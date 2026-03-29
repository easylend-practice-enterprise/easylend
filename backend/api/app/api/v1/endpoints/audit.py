"""Audit log inspection & verification endpoints.

Router prefix: /audit
"""

import logging

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core import audit as audit_core
from app.db.database import get_db
from app.db.models import AuditLog, User
from app.schemas.audit import AuditLogView, AuditVerifyResponse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/audit", tags=["audit"])


def _require_admin(current_user: User = Depends(get_current_user)) -> User:
    if current_user.role is None or current_user.role.role_name.upper() != "ADMIN":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient permissions."
        )
    return current_user


@router.get(
    "/",
    response_model=list[AuditLogView],
    status_code=status.HTTP_200_OK,
    responses={
        401: {"description": "Not authenticated"},
        403: {"description": "Not an admin"},
    },
)
async def list_audit_logs(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=500),
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(_require_admin),
) -> list[AuditLogView]:
    """Return a paginated list of audit logs (admin-only)."""
    result = await db.execute(
        select(AuditLog).order_by(AuditLog.created_at.desc()).offset(skip).limit(limit)
    )
    logs = result.scalars().all()
    return [AuditLogView.model_validate(log) for log in logs]


@router.get(
    "/verify",
    response_model=AuditVerifyResponse,
    status_code=status.HTTP_200_OK,
    responses={
        401: {"description": "Not authenticated"},
        403: {"description": "Not an admin"},
    },
)
async def verify_audit_chain(
    db: AsyncSession = Depends(get_db), _admin: User = Depends(_require_admin)
) -> AuditVerifyResponse:
    """Verify the integrity of the audit chain.

    Deterministic ordering is enforced via `created_at.asc(), audit_id.asc()`.
    The verification walks the chain, checking previous_hash continuity and
    recomputing each record's current_hash.
    """
    result = await db.execute(
        select(AuditLog).order_by(AuditLog.created_at.asc(), AuditLog.audit_id.asc())
    )
    logs = result.scalars().all()

    # An empty audit table is considered a valid (empty) chain by design.
    # It cannot have been tampered with and has no records to protect yet.
    if not logs:
        return AuditVerifyResponse(is_valid=True, tampered_record_id=None)

    running_hash = audit_core._GENESIS_AUDIT_HASH
    for log in logs:
        # Check continuity
        if log.previous_hash != running_hash:
            return AuditVerifyResponse(is_valid=False, tampered_record_id=log.audit_id)

        # Recompute current hash from running_hash and payload
        expected_current = audit_core._compute_audit_hash(
            running_hash, log.action_type, log.payload or {}
        )
        if expected_current != log.current_hash:
            return AuditVerifyResponse(is_valid=False, tampered_record_id=log.audit_id)

        running_hash = log.current_hash

    return AuditVerifyResponse(is_valid=True, tampered_record_id=None)
