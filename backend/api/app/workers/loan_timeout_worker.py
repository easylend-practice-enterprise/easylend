import asyncio
import logging
from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import OperationalError

from app.core.audit import log_audit_event
from app.core.redis_utils import acquire_distributed_lock
from app.core.state_machine import InvalidLoanTransitionError, LoanStateMachine
from app.db.database import AsyncSessionLocal
from app.db.models import Asset, Loan, LoanStatus, Locker

logger = logging.getLogger(__name__)

DEFAULT_TIMEOUT_MINUTES = 3
DEFAULT_INTERVAL_SECONDS = 60
BATCH_SIZE = 100
# Distributed lock TTL must be strictly shorter than the run interval (60s).
# A crashed holder will release the lock after 55s, allowing the next scheduled
# run to proceed without waiting for a full interval.
DISTRIBUTED_LOCK_TTL_SECONDS = 55


async def _process_single_reserved_loan(
    loan_id: UUID,
    reference_now: datetime,
    timeout_minutes: int,
) -> bool:
    """
    Process one RESERVED loan timeout in its own transaction.

    Acquires a NOWAIT lock on the loan, asset, and locker rows before mutating.
    If any row is already locked (e.g. concurrent checkout), skips cleanly.

    Returns True if the loan was transitioned, False otherwise.
    """
    cutoff = reference_now - timedelta(minutes=timeout_minutes)
    async with AsyncSessionLocal() as db:
        try:
            # Lock loan row first (deterministic order: Asset -> Locker).
            loan_result = await db.execute(
                select(Loan).where(Loan.loan_id == loan_id).with_for_update(nowait=True)
            )
        except OperationalError:
            # Another transaction holds the loan lock — skip.
            return False

        loan = loan_result.scalar_one_or_none()
        if loan is None:
            return False

        # Re-check conditions inside the row lock (TOCTOU prevention).
        if loan.loan_status != LoanStatus.RESERVED:
            return False
        if loan.reserved_at is None or loan.reserved_at >= cutoff:
            return False

        # Lock related rows in deterministic order (Asset -> Locker).
        asset = None
        locker = None
        try:
            asset_result = await db.execute(
                select(Asset)
                .where(Asset.asset_id == loan.asset_id)
                .with_for_update(nowait=True)
            )
            asset = asset_result.scalar_one_or_none()

            if loan.checkout_locker_id is not None:
                locker_result = await db.execute(
                    select(Locker)
                    .where(Locker.locker_id == loan.checkout_locker_id)
                    .with_for_update(nowait=True)
                )
                locker = locker_result.scalar_one_or_none()
        except OperationalError:
            # A related row is locked — skip this loan, retry next cycle.
            return False

        # Apply state mutations inside the lock.
        try:
            transition = LoanStateMachine.transition(
                loan.loan_status,
                LoanStatus.PENDING_INSPECTION,
            )
        except InvalidLoanTransitionError:
            logger.warning(
                "Skipping loan timeout due to illegal transition for loan_id=%s",
                loan.loan_id,
            )
            return False

        loan.loan_status = transition.loan_status

        locker_id: str | None = None
        if locker is not None:
            if transition.locker_status is not None:
                locker.locker_status = transition.locker_status
            locker_id = str(locker.locker_id)

        if asset is not None:
            if transition.asset_status is not None:
                asset.asset_status = transition.asset_status
            asset.locker_id = locker.locker_id if locker is not None else None

        payload = {
            "event": "reserved_loan_timeout",
            "loan_id": str(loan.loan_id),
            "locker_id": locker_id,
            "cutoff": cutoff.isoformat(),
        }
        await log_audit_event(
            db,
            action_type="LOAN_RESERVED_TIMEOUT",
            payload=payload,
        )
        await db.commit()
        return True


async def process_reserved_loan_timeouts(
    *,
    now: datetime | None = None,
    timeout_minutes: int = DEFAULT_TIMEOUT_MINUTES,
) -> int:
    """
    Mark RESERVED loans that have exceeded the timeout as PENDING_INSPECTION.

    Fetches loan IDs in batches then processes each individually in its own
    transaction with per-row NOWAIT locks. One loan failure does not affect others.

    Args:
        now: Optional reference time (defaults to utcnow). Exposed for testing.
        timeout_minutes: Minutes after reserved_at after which a loan times out.

    Returns:
        The number of loans transitioned to PENDING_INSPECTION.
    """
    reference_now = now or datetime.now(UTC)
    total_processed = 0
    failed_ids: set[UUID] = set()

    while True:
        cutoff = reference_now - timedelta(minutes=timeout_minutes)
        async with AsyncSessionLocal() as db:
            query = (
                select(Loan.loan_id)
                .where(
                    Loan.loan_status == LoanStatus.RESERVED,
                    Loan.reserved_at.is_not(None),
                    Loan.reserved_at < cutoff,
                    Loan.asset.has(is_deleted=False),
                )
                .order_by(Loan.reserved_at)
            )

            if failed_ids:
                query = query.where(Loan.loan_id.not_in(failed_ids))

            result = await db.execute(query.limit(BATCH_SIZE))
            batch_ids = list(result.scalars().all())

        if not batch_ids:
            break

        for loan_id in batch_ids:
            try:
                processed = await _process_single_reserved_loan(
                    loan_id,
                    reference_now,
                    timeout_minutes,
                )
                if processed:
                    total_processed += 1
            except Exception:
                logger.exception("Failed to process timeout for loan_id=%s", loan_id)
                failed_ids.add(loan_id)
                # Continue to next loan.

    return total_processed


async def reserved_loan_timeout_worker_loop(
    stop_event: asyncio.Event,
    *,
    interval_seconds: int = DEFAULT_INTERVAL_SECONDS,
    timeout_minutes: int = DEFAULT_TIMEOUT_MINUTES,
) -> None:
    while not stop_event.is_set():
        try:
            lock_acquired = await acquire_distributed_lock(
                "lock:loan-timeout-worker",
                DISTRIBUTED_LOCK_TTL_SECONDS,
            )
            if lock_acquired:
                processed = await process_reserved_loan_timeouts(
                    timeout_minutes=timeout_minutes,
                )
                if processed:
                    logger.info(
                        "Reserved-loan timeout worker: marked %d loan(s) as PENDING_INSPECTION.",
                        processed,
                    )
            else:
                logger.debug(
                    "Reserved-loan timeout worker: lock held by another instance, skipping this cycle."
                )
        except Exception:
            logger.exception("Reserved-loan timeout worker iteration failed")

        try:
            await asyncio.wait_for(stop_event.wait(), timeout=interval_seconds)
        except TimeoutError:
            pass


def start_reserved_loan_timeout_worker(
    *,
    interval_seconds: int = DEFAULT_INTERVAL_SECONDS,
    timeout_minutes: int = DEFAULT_TIMEOUT_MINUTES,
) -> tuple[asyncio.Task, asyncio.Event]:
    stop_event = asyncio.Event()
    task = asyncio.create_task(
        reserved_loan_timeout_worker_loop(
            stop_event,
            interval_seconds=interval_seconds,
            timeout_minutes=timeout_minutes,
        ),
        name="reserved-loan-timeout-worker",
    )
    return task, stop_event


async def stop_reserved_loan_timeout_worker(
    task: asyncio.Task,
    stop_event: asyncio.Event,
) -> None:
    stop_event.set()
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass


async def process_timeouts() -> int:
    """Run a single timeout-processing cycle."""
    return await process_reserved_loan_timeouts()


if __name__ == "__main__":
    asyncio.run(process_timeouts())
