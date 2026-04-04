import asyncio
import logging
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import OperationalError

from app.core.audit import log_audit_event
from app.core.redis_utils import acquire_distributed_lock
from app.db.database import AsyncSessionLocal
from app.db.models import Loan, LoanStatus

logger = logging.getLogger(__name__)

DEFAULT_INTERVAL_HOURS = 1
BATCH_SIZE = 100
# Distributed lock TTL must be strictly shorter than the run interval to ensure
# the lock is released before the next expected run.
DISTRIBUTED_LOCK_TTL_SECONDS = 3500


async def _process_single_loan(
    loan_id: UUID,
    reference_now: datetime,
) -> bool:
    """
    Process one overdue loan in its own transaction.

    Acquires a NOWAIT lock on the specific loan row before mutating. If the row
    is already locked (e.g. concurrent checkout), skips this loan cleanly.

    Returns True if the loan was successfully marked OVERDUE, False otherwise.
    """
    async with AsyncSessionLocal() as db:
        try:
            result = await db.execute(
                select(Loan).where(Loan.loan_id == loan_id).with_for_update(nowait=True)
            )
        except OperationalError:
            # Another worker has the row locked — skip.
            return False

        loan = result.scalar_one_or_none()
        if loan is None:
            return False

        # Re-check conditions inside the row lock to prevent TOCTOU races.
        if loan.loan_status != LoanStatus.ACTIVE:
            return False
        if loan.due_date is None or loan.due_date >= reference_now:
            return False

        loan.loan_status = LoanStatus.OVERDUE
        await log_audit_event(
            db,
            action_type="LOAN_OVERDUE",
            payload={
                "loan_id": str(loan.loan_id),
                "asset_id": str(loan.asset_id),
            },
        )
        await db.commit()
        return True


async def process_overdue_loans(
    *,
    now: datetime | None = None,
) -> int:
    """
    Mark ACTIVE loans past their due_date as OVERDUE.

    Fetches loan IDs in batches (no lock held on the result set) then processes
    each loan individually in its own transaction with a per-row NOWAIT lock.
    A distributed Redis lock ensures only one worker instance runs per interval.

    Args:
        now: Optional reference time (defaults to utcnow). Exposed for testing.

    Returns:
        The number of loans that were transitioned to OVERDUE.
    """
    reference_now = now or datetime.now(UTC)
    total_processed = 0
    failed_ids: set[UUID] = set()

    while True:
        # Fetch a batch of overdue loan IDs only (no row lock held on this result).
        # Using yield_per would keep a cursor open — fetching IDs in small batches
        # achieves the same memory safety without cursor complexity.
        async with AsyncSessionLocal() as db:
            query = (
                select(Loan.loan_id)
                .where(
                    Loan.loan_status == LoanStatus.ACTIVE,
                    Loan.due_date.is_not(None),
                    Loan.due_date < reference_now,
                    Loan.asset.has(is_deleted=False),
                )
                .order_by(Loan.due_date)
            )

            if failed_ids:
                query = query.where(Loan.loan_id.not_in(failed_ids))

            result = await db.execute(query.limit(BATCH_SIZE))
            batch_ids = list(result.scalars().all())

        if not batch_ids:
            break

        for loan_id in batch_ids:
            try:
                processed = await _process_single_loan(loan_id, reference_now)
                if processed:
                    total_processed += 1
            except Exception:
                logger.exception("Failed to process overdue loan_id=%s", loan_id)
                failed_ids.add(loan_id)
                # Continue to next loan — one failure must not stop the batch.

    return total_processed


async def overdue_worker_loop(
    stop_event: asyncio.Event,
    *,
    interval_hours: int = DEFAULT_INTERVAL_HOURS,
) -> None:
    interval_seconds = interval_hours * 3600
    while not stop_event.is_set():
        try:
            # Distributed lock: only one instance of the worker runs per interval.
            lock_acquired = await acquire_distributed_lock(
                "lock:overdue-worker",
                DISTRIBUTED_LOCK_TTL_SECONDS,
            )
            if lock_acquired:
                processed = await process_overdue_loans()
                if processed:
                    logger.info(
                        "Overdue worker: marked %d loan(s) as OVERDUE.",
                        processed,
                    )
            else:
                logger.debug(
                    "Overdue worker: lock held by another instance, skipping this cycle."
                )
        except Exception:
            logger.exception("Overdue worker iteration failed")

        try:
            await asyncio.wait_for(stop_event.wait(), timeout=interval_seconds)
        except TimeoutError:
            pass


def start_overdue_worker(
    *,
    interval_hours: int = DEFAULT_INTERVAL_HOURS,
) -> tuple[asyncio.Task, asyncio.Event]:
    stop_event = asyncio.Event()
    task = asyncio.create_task(
        overdue_worker_loop(
            stop_event,
            interval_hours=interval_hours,
        ),
        name="overdue-worker",
    )
    return task, stop_event


async def stop_overdue_worker(
    task: asyncio.Task,
    stop_event: asyncio.Event,
) -> None:
    stop_event.set()
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass
