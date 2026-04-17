import asyncio
import logging
import secrets
import uuid
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError, OperationalError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.deps import get_current_admin, get_current_user
from app.core import security
from app.core.audit import log_audit_event
from app.core.db_utils import is_lock_not_available_error
from app.db.database import get_db
from app.db.models import (
    AIEvaluation,
    AuditLog,
    Loan,
    LoanStatus,
    Role,
    User,
    UserStatus,
)
from app.db.redis import revoke_all_refresh_tokens
from app.schemas.user import (
    UserCreate,
    UserListResponse,
    UserNfcUpdate,
    UserResponse,
    UserUpdate,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/users", tags=["users"])


async def _get_user_with_role_or_404(db: AsyncSession, user_id: UUID) -> User:
    result = await db.execute(
        select(User).options(selectinload(User.role)).where(User.user_id == user_id)
    )
    user = result.scalar_one_or_none()
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found.",
        )
    return user


@router.get(
    "",
    response_model=UserListResponse,
    status_code=status.HTTP_200_OK,
    responses={
        401: {"description": "Not authenticated"},
        403: {"description": "Forbidden"},
    },
)
async def list_users(
    skip: int = Query(
        0,
        ge=0,
        description="Number of users to skip before returning results (pagination offset).",
    ),
    limit: int = Query(
        100,
        ge=1,
        le=1000,
        description="Maximum number of users to return in a single response (pagination page size).",
    ),
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_admin),
) -> UserListResponse:
    """
    List users with pagination.

    Requires Admin role.
    """
    result = await db.execute(
        select(User)
        .options(selectinload(User.role))
        .order_by(User.user_id)
        .offset(skip)
        .limit(limit)
    )
    users_data = [UserResponse.model_validate(u) for u in result.scalars().all()]

    total_result = await db.execute(select(func.count()).select_from(User))
    total = total_result.scalar_one_or_none() or 0

    return UserListResponse(items=users_data, total=total)


@router.get(
    "/me",
    response_model=UserResponse,
    status_code=status.HTTP_200_OK,
    responses={
        401: {"description": "Not authenticated"},
    },
)
async def get_me(current_user: User = Depends(get_current_user)) -> User:
    """
    Return the profile of the currently authenticated user.

    Requires authentication.
    """
    return current_user


@router.get(
    "/{user_id}",
    response_model=UserResponse,
    status_code=status.HTTP_200_OK,
    responses={
        401: {"description": "Not authenticated"},
        403: {"description": "Forbidden"},
        404: {"description": "Not found"},
    },
)
async def get_user_by_id(
    user_id: UUID,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_admin),
) -> User:
    """
    Return a user by unique identifier.

    Requires Admin role.
    """
    return await _get_user_with_role_or_404(db, user_id)


@router.post(
    "",
    response_model=UserResponse,
    status_code=status.HTTP_201_CREATED,
    responses={
        400: {"description": "Bad request"},
        401: {"description": "Not authenticated"},
        403: {"description": "Forbidden"},
    },
)
async def create_user(
    payload: UserCreate,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_admin),
) -> User:
    """
    Create a new user account.

    Requires Admin role.
    """
    existing_email = await db.execute(
        select(User).where(User.email == str(payload.email))
    )
    if existing_email.scalar_one_or_none() is not None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email address already exists.",
        )

    role_exists = await db.execute(
        select(Role.role_id).where(Role.role_id == payload.role_id)
    )
    if role_exists.scalar_one_or_none() is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid role_id.",
        )

    if payload.nfc_tag_id is not None:
        existing_nfc = await db.execute(
            select(User).where(User.nfc_tag_id == payload.nfc_tag_id)
        )
        if existing_nfc.scalar_one_or_none() is not None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="NFC tag is already linked to another user.",
            )

    user = User(
        role_id=payload.role_id,
        first_name=payload.first_name,
        last_name=payload.last_name,
        email=str(payload.email),
        nfc_tag_id=payload.nfc_tag_id,
        pin_hash=security.get_pin_hash(payload.pin),
        accepted_privacy_policy=payload.accepted_privacy_policy,
    )

    db.add(user)
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email address or NFC tag already exists.",
        )

    return await _get_user_with_role_or_404(db, user.user_id)


@router.patch(
    "/{user_id}",
    response_model=UserResponse,
    status_code=status.HTTP_200_OK,
    responses={
        400: {"description": "Bad request"},
        401: {"description": "Not authenticated"},
        403: {"description": "Forbidden"},
        404: {"description": "Not found"},
    },
)
async def update_user(
    user_id: UUID,
    payload: UserUpdate,
    db: AsyncSession = Depends(get_db),
    current_admin: User = Depends(get_current_admin),
) -> User:
    """
    Partially update an existing user.

    Requires Admin role.
    """
    user = await _get_user_with_role_or_404(db, user_id)

    # Capture old status for audit logging before any mutations
    old_status = user.status

    update_data = payload.model_dump(exclude_unset=True)

    # Prevent non-nullable columns from being explicitly set to None
    non_nullable_fields = {"email", "role_id", "first_name", "last_name", "status"}
    invalid_null_fields = [
        field
        for field in non_nullable_fields
        if field in update_data and update_data[field] is None
    ]
    if invalid_null_fields:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Request contains fields that cannot be set to null.",
        )

    if "status" in payload.model_fields_set and payload.status is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="User status cannot be set to null.",
        )

    if "email" in update_data and update_data["email"] is not None:
        new_email = str(update_data["email"])
        existing_email = await db.execute(
            select(User).where(User.email == new_email, User.user_id != user_id)
        )
        if existing_email.scalar_one_or_none() is not None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Email address already exists.",
            )
        update_data["email"] = new_email

    if "nfc_tag_id" in update_data and update_data["nfc_tag_id"] is not None:
        existing_nfc = await db.execute(
            select(User).where(
                User.nfc_tag_id == update_data["nfc_tag_id"],
                User.user_id != user_id,
            )
        )
        if existing_nfc.scalar_one_or_none() is not None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="NFC tag is already linked to another user.",
            )

    if "role_id" in update_data and update_data["role_id"] is not None:
        role_exists = await db.execute(
            select(Role.role_id).where(Role.role_id == update_data["role_id"])
        )
        if role_exists.scalar_one_or_none() is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid role_id.",
            )

    if "pin" in update_data and update_data["pin"] is not None:
        update_data["pin_hash"] = security.get_pin_hash(update_data.pop("pin"))
    else:
        update_data.pop("pin", None)

    old_pin_hash = getattr(user, "pin_hash", None)

    for field, value in update_data.items():
        setattr(user, field, value)

    if update_data.get("status") == UserStatus.ANONYMIZED:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot set status to ANONYMIZED via update. Use the dedicated /anonymize endpoint.",
        )

    new_status = update_data.get("status")

    try:
        await db.flush()
        if new_status is not None and new_status != old_status:
            await log_audit_event(
                db,
                action_type="USER_STATUS_CHANGED",
                payload={
                    "target_user_id": str(user_id),
                    "old_status": getattr(old_status, "value", old_status),
                    "new_status": getattr(new_status, "value", new_status),
                },
                user_id=current_admin.user_id,
            )
        if "pin_hash" in update_data and update_data["pin_hash"] != old_pin_hash:
            await log_audit_event(
                db,
                action_type="USER_PIN_CHANGED",
                payload={
                    "target_user_id": str(user_id),
                },
                user_id=current_admin.user_id,
            )
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email address or NFC tag already exists.",
        )

    return await _get_user_with_role_or_404(db, user_id)


@router.post(
    "/{user_id}/anonymize",
    response_model=UserResponse,
    status_code=status.HTTP_200_OK,
    responses={
        400: {"description": "User already anonymized"},
        401: {"description": "Not authenticated"},
        403: {"description": "Forbidden"},
        404: {"description": "User not found"},
    },
)
async def anonymize_user(
    user_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_admin: User = Depends(get_current_admin),
) -> User:
    """
    Anonymize a user account (GDPR Right to be Forgotten).

    Replaces all PII fields (first_name, last_name, email, nfc_tag_id) with
    non-identifying placeholder values and replaces pin_hash with a hash of a
    randomly generated credential, effectively disabling login with the original PIN.
    Also sets status=UserStatus.ANONYMIZED.
    Writes an audit log entry with action_type="USER_ANONYMIZED".

    Requires Admin role.
    """
    try:
        result = await db.execute(
            select(User).where(User.user_id == user_id).with_for_update(nowait=True)
        )
    except OperationalError as exc:
        await db.rollback()
        if is_lock_not_available_error(exc):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="User is currently being modified. Please retry.",
            )
        raise

    user = result.scalar_one_or_none()
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="User not found."
        )

    if user.status == UserStatus.ANONYMIZED:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="User is already anonymized.",
        )

    # Block anonymization if user has active/reserved/overdue loans
    active_loans_count_result = await db.execute(
        select(func.count())
        .select_from(Loan)
        .where(
            Loan.user_id == user_id,
            Loan.loan_status.in_(
                [LoanStatus.RESERVED, LoanStatus.ACTIVE, LoanStatus.OVERDUE]
            ),
        )
    )
    if (active_loans_count_result.scalar_one_or_none() or 0) > 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot anonymize user with active, reserved, or overdue loans.",
        )

    for attempt in range(3):
        try:
            user.first_name = "Anonymized"
            user.last_name = "User"
            user.email = f"anon_{uuid.uuid4()}@easylend.local"
            user.nfc_tag_id = None
            user.pin_hash = security.get_pin_hash(secrets.token_urlsafe(16))
            user.status = UserStatus.ANONYMIZED
            user.ban_reason = None
            user.failed_login_attempts = 0
            user.locked_until = None

            # Atomic: audit event is staged before the single commit that covers both
            # user mutations and the audit log entry — rollback covers both on failure.
            await log_audit_event(
                db,
                action_type="USER_ANONYMIZED",
                payload={"target_user_id": str(user_id)},
                user_id=current_admin.user_id,
            )
            await db.commit()

            # After successful commit: revoke tokens (non-critical-path, best-effort)
            try:
                await revoke_all_refresh_tokens(str(user_id))
            except Exception:
                logger.exception(
                    "revoke_all_refresh_tokens failed for user %s — best-effort, non-critical",
                    user_id,
                )

            break
        except (IntegrityError, OperationalError):
            await db.rollback()
            logger.warning(
                f"Database error during anonymization, retrying attempt {attempt + 1}/3..."
            )
            await asyncio.sleep(0.1 * (2**attempt))
            if attempt == 2:
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="Anonymization failed after multiple attempts. Please try again.",
                )

    return await _get_user_with_role_or_404(db, user_id)


@router.patch(
    "/{user_id}/nfc",
    response_model=UserResponse,
    status_code=status.HTTP_200_OK,
    responses={
        400: {"description": "Bad request"},
        401: {"description": "Not authenticated"},
        403: {"description": "Forbidden"},
        404: {"description": "Not found"},
    },
)
async def update_user_nfc(
    user_id: UUID,
    payload: UserNfcUpdate,
    db: AsyncSession = Depends(get_db),
    current_admin: User = Depends(get_current_admin),
) -> User:
    """
    Update the NFC tag linked to a user account.

    Requires Admin role.
    """
    user = await _get_user_with_role_or_404(db, user_id)

    existing_nfc = await db.execute(
        select(User).where(
            User.nfc_tag_id == payload.nfc_tag_id, User.user_id != user_id
        )
    )
    if existing_nfc.scalar_one_or_none() is not None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="NFC tag is already linked to another user.",
        )

    user.nfc_tag_id = payload.nfc_tag_id
    await log_audit_event(
        db,
        action_type="USER_NFC_ASSIGNED",
        payload={
            "target_user_id": str(user_id),
            "nfc_tag_id": payload.nfc_tag_id,
        },
        user_id=current_admin.user_id,
    )
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="NFC tag is already linked to another user.",
        )
    return await _get_user_with_role_or_404(db, user_id)


@router.get(
    "/{user_id}/export",
    status_code=status.HTTP_200_OK,
    responses={
        401: {"description": "Not authenticated"},
        403: {"description": "Forbidden"},
        404: {"description": "User not found"},
    },
)
async def export_user_data(
    user_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    """
    Export all personal data for a user (GDPR Right to Portability).

    Accessible by the user themselves OR an Admin. Raises 403 otherwise.
    """
    if (
        current_user.user_id != user_id
        and current_user.role.role_name.upper() != "ADMIN"
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Forbidden.",
        )

    user = await _get_user_with_role_or_404(db, user_id)

    # Fetch all loans with asset, evaluations, and damage reports eagerly loaded
    loans_result = await db.execute(
        select(Loan)
        .options(
            selectinload(Loan.asset),
            selectinload(Loan.evaluations).selectinload(AIEvaluation.damage_reports),
        )
        .where(Loan.user_id == user_id)
        .order_by(Loan.reserved_at.desc())
        .limit(1000)
    )
    all_loans = []
    for loan in loans_result.scalars().all():
        loan_dict = {
            "loan_id": str(loan.loan_id),
            "asset_name": loan.asset.name if loan.asset else None,
            "status": loan.loan_status,
            "reserved_at": (loan.reserved_at.isoformat() if loan.reserved_at else None),
            "borrowed_at": (loan.borrowed_at.isoformat() if loan.borrowed_at else None),
            "due_date": (loan.due_date.isoformat() if loan.due_date else None),
            "returned_at": (loan.returned_at.isoformat() if loan.returned_at else None),
            "checkout_locker_id": str(loan.checkout_locker_id)
            if loan.checkout_locker_id
            else None,
            "return_locker_id": str(loan.return_locker_id)
            if loan.return_locker_id
            else None,
            "evaluations": [
                {
                    "evaluation_id": str(ev.evaluation_id),
                    "evaluation_type": ev.evaluation_type,
                    "ai_confidence": ev.ai_confidence,
                    "has_damage_detected": ev.has_damage_detected,
                    "is_approved": ev.is_approved,
                    "rejection_reason": ev.rejection_reason,
                    "analyzed_at": (
                        ev.analyzed_at.isoformat() if ev.analyzed_at else None
                    ),
                    "damage_reports": [
                        {
                            "damage_type": dr.damage_type,
                            "severity": dr.severity,
                            "requires_repair": dr.requires_repair,
                        }
                        for dr in ev.damage_reports
                    ],
                }
                for ev in loan.evaluations
            ],
        }
        all_loans.append(loan_dict)

    # Fetch audit history
    audit_result = await db.execute(
        select(AuditLog)
        .where(
            or_(
                AuditLog.user_id == user_id,
                AuditLog.payload["target_user_id"].as_string() == str(user_id),
                AuditLog.payload["user_id"].as_string() == str(user_id),
            )
        )
        .order_by(AuditLog.created_at)
        .limit(1000)
    )
    audit_history = [
        {
            "action_type": log.action_type,
            "payload": (
                {
                    k: (
                        "[REDACTED]"
                        if k in ("first_name", "last_name", "email", "target_user_id")
                        else v
                    )
                    for k, v in log.payload.items()
                }
                if (user.status == UserStatus.ANONYMIZED and log.payload)
                else log.payload
            ),
            "created_at": (log.created_at.isoformat() if log.created_at else None),
        }
        for log in audit_result.scalars().all()
    ]

    return {
        "user": {
            "user_id": str(user.user_id),
            "first_name": "[REDACTED]"
            if user.status == UserStatus.ANONYMIZED
            else user.first_name,
            "last_name": "[REDACTED]"
            if user.status == UserStatus.ANONYMIZED
            else user.last_name,
            "email": "[REDACTED]"
            if user.status == UserStatus.ANONYMIZED
            else user.email,
            "role_name": user.role.role_name,
            "nfc_tag_id": user.nfc_tag_id,
            "status": user.status,
            "accepted_privacy_policy": user.accepted_privacy_policy,
        },
        "loans": all_loans,
        "audit_history": audit_history,
    }
