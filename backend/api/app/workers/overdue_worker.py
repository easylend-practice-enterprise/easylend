import asyncio
import logging
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select

from app.core.audit import log_audit_event
from app.db.database import AsyncSessionLocal
from app.db.models import Loan, LoanStatus

logger = logging.getLogger(__name__)

DEFAULT_INTERVAL_HOURS = 1


async def process_overdue_loans(
    db: Any,
    *,
    now: datetime | None = None,
) -> int:
    """Mark ACTIVE loans past their due_date as OVERDUE.

    Args:
        db: An AsyncSession instance.
        now: Optional reference time (defaults to utcnow). Exposed for testing.

    Returns:
        The number of loans that were transitioned to OVERDUE.
    """
    reference_now = now or datetime.now(UTC)

    overdue_result = await db.execute(
        select(Loan)
        .where(
            Loan.loan_status == LoanStatus.ACTIVE,
            Loan.due_date.is_not(None),
            Loan.due_date < reference_now,
            Loan.asset.has(is_deleted=False),
        )
        .with_for_update(skip_locked=True)
    )
    overdue_loans = overdue_result.scalars().all()

    if not overdue_loans:
        return 0

    for loan in overdue_loans:
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
    return len(overdue_loans)


async def overdue_worker_loop(
    stop_event: asyncio.Event,
    *,
    interval_hours: int = DEFAULT_INTERVAL_HOURS,
) -> None:
    interval_seconds = interval_hours * 3600
    while not stop_event.is_set():
        try:
            async with AsyncSessionLocal() as db:
                await process_overdue_loans(db)
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
