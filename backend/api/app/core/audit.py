import asyncio
import hashlib
import json
import logging
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.engine import Result
from sqlalchemy.exc import OperationalError
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import AuditLog

logger = logging.getLogger(__name__)

_GENESIS_AUDIT_HASH = "0" * 64


def _compute_audit_hash(previous_hash: str, action_type: str, payload: dict) -> str:
    payload_json = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    digest_input = f"{previous_hash}|{action_type}|{payload_json}"
    return hashlib.sha256(digest_input.encode("utf-8")).hexdigest()


async def log_audit_event(
    db: AsyncSession,
    action_type: str,
    payload: dict | None,
    user_id: UUID | None = None,
) -> AuditLog:
    """Write an audit log entry with hash-chain integrity.

    Uses `FOR UPDATE NOWAIT` to acquire a lock on the most-recent audit row
    without blocking concurrent writers. If the lock is already held, the call
    is retried with exponential backoff up to 5 times; if contention persists,
    the error is propagated so callers can handle it.
    """
    # Retry up to 5 times with exponential backoff to handle transient lock contention.
    # Base delay 50ms, doubles each retry: 50ms → 100ms → 200ms → 400ms → 800ms.
    MAX_ATTEMPTS = 5
    BASE_DELAY = 0.05
    last_audit_result: Result | None = None
    for attempt in range(MAX_ATTEMPTS):
        try:
            last_audit_result = await db.execute(
                select(AuditLog)
                .order_by(AuditLog.created_at.desc(), AuditLog.audit_id.desc())
                .limit(1)
                .with_for_update(nowait=True)
            )
            break
        except OperationalError:
            if attempt < MAX_ATTEMPTS - 1:
                delay = BASE_DELAY * (2**attempt)
                logger.warning(
                    "Audit log lock contention (attempt %d/%d), retrying in %.3fs.",
                    attempt + 1,
                    MAX_ATTEMPTS,
                    delay,
                )
                await asyncio.sleep(delay)
                continue
            # Last attempt exhausted — propagate
            raise

    if last_audit_result is None:
        raise RuntimeError("Audit log result cannot be None")
    last_audit = last_audit_result.scalar_one_or_none()
    # Normalise None payload to empty dict — ensures the stored value and
    # the hash computation are always consistent (null != {} in JSON).
    payload = payload or {}
    previous_hash = (
        last_audit.current_hash if last_audit is not None else _GENESIS_AUDIT_HASH
    )
    current_hash = _compute_audit_hash(previous_hash, action_type, payload)

    audit_log = AuditLog(
        user_id=user_id,
        action_type=action_type,
        payload=payload,
        previous_hash=previous_hash,
        current_hash=current_hash,
    )
    db.add(audit_log)
    return audit_log
