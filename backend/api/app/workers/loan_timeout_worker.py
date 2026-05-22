import asyncio
import logging
from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import case, or_, select
from sqlalchemy.exc import OperationalError

from app.core.audit import log_audit_event
from app.core.config import settings
from app.core.redis_utils import acquire_distributed_lock
from app.core.state_machine import InvalidLoanTransitionError, LoanStateMachine
from app.db.database import AsyncSessionLocal
from app.db.models import Asset, AssetStatus, Loan, LoanStatus, Locker, LockerStatus

logger = logging.getLogger(__name__)

DEFAULT_TIMEOUT_MINUTES = settings.LOAN_TIMEOUT_WORKER_TIMEOUT_MINUTES
DEFAULT_INTERVAL_SECONDS = settings.LOAN_TIMEOUT_WORKER_INTERVAL_SECONDS
BATCH_SIZE = settings.LOAN_TIMEOUT_WORKER_BATCH_SIZE
# Distributed lock TTL must be strictly shorter than the run interval (60s).
# A crashed holder will release the lock after 55s, allowing the next scheduled
# run to proceed without waiting for a full interval.
DISTRIBUTED_LOCK_TTL_SECONDS = settings.LOAN_TIMEOUT_WORKER_LOCK_TTL_SECONDS


async def _process_single_timed_out_loan(
    loan_id: UUID,
    reference_now: datetime,
    timeout_minutes: int,
) -> bool:
    """
    Process one timed-out RESERVED or RETURNING loan in its own transaction.

    Acquires a NOWAIT lock on the loan, asset, and locker rows before mutating.
    If any row is already locked (e.g. concurrent checkout/return), skips cleanly.

    Returns True if the loan was transitioned, False otherwise.
    """
    cutoff = reference_now - timedelta(minutes=timeout_minutes)
    async with AsyncSessionLocal() as db:
        try:
            loan_result = await db.execute(
                select(Loan).where(Loan.loan_id == loan_id).with_for_update(nowait=True)
            )
        except OperationalError:
            return False

        loan = loan_result.scalar_one_or_none()
        if loan is None:
            return False

        if loan.loan_status not in (LoanStatus.RESERVED, LoanStatus.RETURNING):
            return False

        if loan.loan_status == LoanStatus.RESERVED:
            if loan.reserved_at is None or loan.reserved_at >= cutoff:
                return False
        elif loan.loan_status == LoanStatus.RETURNING:
            if loan.updated_at is None or loan.updated_at >= cutoff:
                return False

        asset = None
        checkout_locker = None
        return_locker = None
        try:
            asset_result = await db.execute(
                select(Asset)
                .where(Asset.asset_id == loan.asset_id)
                .with_for_update(nowait=True)
            )
            asset = asset_result.scalar_one_or_none()

            if loan.checkout_locker_id is not None:
                checkout_locker_result = await db.execute(
                    select(Locker)
                    .where(Locker.locker_id == loan.checkout_locker_id)
                    .with_for_update(nowait=True)
                )
                checkout_locker = checkout_locker_result.scalar_one_or_none()

            if loan.return_locker_id is not None:
                return_locker_result = await db.execute(
                    select(Locker)
                    .where(Locker.locker_id == loan.return_locker_id)
                    .with_for_update(nowait=True)
                )
                return_locker = return_locker_result.scalar_one_or_none()
        except OperationalError:
            return False

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

        original_status = loan.loan_status
        loan.loan_status = transition.loan_status

        checkout_locker_id_str: str | None = None
        return_locker_id_str: str | None = None

        if original_status == LoanStatus.RESERVED:
            if checkout_locker is not None:
                if transition.locker_status is not None:
                    checkout_locker.locker_status = transition.locker_status
                checkout_locker_id_str = str(checkout_locker.locker_id)
            if asset is not None:
                if transition.asset_status is not None:
                    asset.asset_status = transition.asset_status
                asset.locker_id = (
                    checkout_locker.locker_id if checkout_locker is not None else None
                )
        elif original_status == LoanStatus.RETURNING:
            if asset is not None:
                asset.asset_status = AssetStatus.PENDING_INSPECTION
            if checkout_locker is not None:
                checkout_locker.locker_status = LockerStatus.MAINTENANCE
                checkout_locker_id_str = str(checkout_locker.locker_id)
            if return_locker is not None:
                return_locker.locker_status = LockerStatus.MAINTENANCE
                return_locker_id_str = str(return_locker.locker_id)

        payload = {
            "event": "loan_timeout",
            "loan_id": str(loan.loan_id),
            "original_status": original_status.value,
            "checkout_locker_id": checkout_locker_id_str,
            "return_locker_id": return_locker_id_str,
            "cutoff": cutoff.isoformat(),
        }
        await log_audit_event(
            db,
            action_type="LOAN_RESERVED_TIMEOUT",
            payload=payload,
        )
        await db.commit()
        return True


async def process_timed_out_loans(
    *,
    now: datetime | None = None,
    timeout_minutes: int = DEFAULT_TIMEOUT_MINUTES,
) -> int:
    """
    Mark timed-out RESERVED or RETURNING loans as PENDING_INSPECTION.

    Fetches loan IDs in batches then processes each individually in its own
    transaction with per-row NOWAIT locks. One loan failure does not affect others.

    Args:
        now: Optional reference time (defaults to utcnow). Exposed for testing.
        timeout_minutes: Minutes after reserved_at / returned_at after which a loan times out.

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
                    or_(
                        (Loan.loan_status == LoanStatus.RESERVED)
                        & (Loan.reserved_at.is_not(None))
                        & (Loan.reserved_at < cutoff),
                        (Loan.loan_status == LoanStatus.RETURNING)
                        & (Loan.updated_at.is_not(None))
                        & (Loan.updated_at < cutoff),
                    ),
                    Loan.asset.has(is_deleted=False),
                )
                .order_by(
                    # Order by the relevant timestamp per status to process oldest first
                    case(
                        (Loan.loan_status == LoanStatus.RESERVED, Loan.reserved_at),
                        else_=Loan.updated_at,
                    )
                )
            )

            if failed_ids:
                query = query.where(Loan.loan_id.not_in(failed_ids))

            result = await db.execute(query.limit(BATCH_SIZE))
            batch_ids = list(result.scalars().all())

        if not batch_ids:
            break

        for loan_id in batch_ids:
            try:
                processed = await _process_single_timed_out_loan(
                    loan_id,
                    reference_now,
                    timeout_minutes,
                )
                if processed:
                    total_processed += 1
            except Exception:
                logger.exception("Failed to process timeout for loan_id=%s", loan_id)
                failed_ids.add(loan_id)

    return total_processed


async def timed_out_loan_worker_loop(
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
                processed = await process_timed_out_loans(
                    timeout_minutes=timeout_minutes,
                )
                if processed:
                    logger.info(
                        "Loan-timeout worker: marked %d loan(s) as PENDING_INSPECTION.",
                        processed,
                    )
            else:
                logger.debug(
                    "Loan-timeout worker: lock held by another instance, skipping this cycle."
                )
        except Exception:
            logger.exception("Loan-timeout worker iteration failed")

        try:
            await asyncio.wait_for(stop_event.wait(), timeout=interval_seconds)
        except TimeoutError:
            pass


def start_timed_out_loan_worker(
    *,
    interval_seconds: int = DEFAULT_INTERVAL_SECONDS,
    timeout_minutes: int = DEFAULT_TIMEOUT_MINUTES,
) -> tuple[asyncio.Task, asyncio.Event]:
    stop_event = asyncio.Event()
    task = asyncio.create_task(
        timed_out_loan_worker_loop(
            stop_event,
            interval_seconds=interval_seconds,
            timeout_minutes=timeout_minutes,
        ),
        name="loan-timeout-worker",
    )
    return task, stop_event


async def stop_timed_out_loan_worker(
    task: asyncio.Task,
    stop_event: asyncio.Event,
) -> None:
    stop_event.set()
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass


# Aliases for backwards compatibility
start_reserved_loan_timeout_worker = start_timed_out_loan_worker
stop_reserved_loan_timeout_worker = stop_timed_out_loan_worker
process_reserved_loan_timeouts = process_timed_out_loans


async def process_timeouts() -> int:
    """Run a single timeout-processing cycle."""
    return await process_timed_out_loans()


if __name__ == "__main__":
    asyncio.run(timed_out_loan_worker_loop(asyncio.Event()))
