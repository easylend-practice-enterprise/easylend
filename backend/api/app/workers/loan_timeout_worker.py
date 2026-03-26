import asyncio
import logging
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import select

from app.core.audit import log_audit_event
from app.db.database import AsyncSessionLocal
from app.db.models import Loan, LoanStatus, Locker, LockerStatus

logger = logging.getLogger(__name__)

DEFAULT_TIMEOUT_MINUTES = 3
DEFAULT_INTERVAL_SECONDS = 60


async def process_reserved_loan_timeouts(
    db: Any,
    *,
    now: datetime | None = None,
    timeout_minutes: int = DEFAULT_TIMEOUT_MINUTES,
) -> int:
    reference_now = now or datetime.now(UTC)
    cutoff = reference_now - timedelta(minutes=timeout_minutes)

    timed_out_loans_result = await db.execute(
        select(Loan).where(
            Loan.loan_status == LoanStatus.RESERVED,
            Loan.reserved_at.is_not(None),
            Loan.reserved_at < cutoff,
        )
    )
    timed_out_loans = timed_out_loans_result.scalars().all()

    if not timed_out_loans:
        return 0

    for loan in timed_out_loans:
        loan.loan_status = LoanStatus.PENDING_INSPECTION

        locker_result = await db.execute(
            select(Locker).where(Locker.locker_id == loan.checkout_locker_id)
        )
        locker = locker_result.scalar_one_or_none()
        locker_id = None
        if locker is not None:
            locker.locker_status = LockerStatus.MAINTENANCE
            locker_id = str(locker.locker_id)

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
    return len(timed_out_loans)


async def reserved_loan_timeout_worker_loop(
    stop_event: asyncio.Event,
    *,
    interval_seconds: int = DEFAULT_INTERVAL_SECONDS,
    timeout_minutes: int = DEFAULT_TIMEOUT_MINUTES,
) -> None:
    while not stop_event.is_set():
        try:
            async with AsyncSessionLocal() as db:
                await process_reserved_loan_timeouts(
                    db,
                    timeout_minutes=timeout_minutes,
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
