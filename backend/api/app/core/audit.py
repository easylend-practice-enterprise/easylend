import hashlib
import json
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import AuditLog

_GENESIS_AUDIT_HASH = "0" * 64


def _compute_audit_hash(previous_hash: str, action_type: str, payload: dict) -> str:
    payload_json = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    digest_input = f"{previous_hash}|{action_type}|{payload_json}"
    return hashlib.sha256(digest_input.encode("utf-8")).hexdigest()


async def log_audit_event(
    db: AsyncSession,
    action_type: str,
    payload: dict,
    user_id: UUID | None = None,
) -> AuditLog:
    last_audit_result = await db.execute(
        select(AuditLog).order_by(AuditLog.created_at.desc()).limit(1).with_for_update()
    )
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
