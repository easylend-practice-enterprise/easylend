import secrets
import uuid
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.deps import get_current_admin, get_current_user
from app.core import security
from app.core.audit import log_audit_event
from app.db.database import get_db
from app.db.models import AuditLog, Loan, LoanStatus, Role, User
from app.schemas.user import (
    UserCreate,
    UserListResponse,
    UserNfcUpdate,
    UserResponse,
    UserUpdate,
)

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
    _: User = Depends(get_current_admin),
) -> User:
    """
    Partially update an existing user.

    Requires Admin role.
    """
    user = await _get_user_with_role_or_404(db, user_id)

    update_data = payload.model_dump(exclude_unset=True)

    # Prevent non-nullable columns from being explicitly set to None
    non_nullable_fields = {"email", "role_id", "first_name", "last_name", "is_active"}
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

    for field, value in update_data.items():
        setattr(user, field, value)

    try:
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
    Also sets is_active=False and is_anonymized=True.
    Writes an audit log entry with action_type="USER_ANONYMIZED".

    Requires Admin role.
    """
    user = await _get_user_with_role_or_404(db, user_id)

    if user.is_anonymized:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="User is already anonymized.",
        )

    for attempt in range(3):
        try:
            user.first_name = "Anonymized"
            user.last_name = "User"
            user.email = f"anon_{uuid.uuid4()}@easylend.local"
            user.nfc_tag_id = None
            user.pin_hash = security.get_pin_hash(secrets.token_urlsafe(16))
            user.is_active = False
            user.is_anonymized = True

            await log_audit_event(
                db,
                action_type="USER_ANONYMIZED",
                payload={"target_user_id": str(user_id)},
                user_id=current_admin.user_id,
            )

            await db.commit()
            break
        except IntegrityError:
            await db.rollback()
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
    _: User = Depends(get_current_admin),
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

    # Fetch active loans (load asset relationship eagerly)
    loans_result = await db.execute(
        select(Loan)
        .options(selectinload(Loan.asset))
        .where(
            Loan.user_id == user_id,
            Loan.loan_status.in_(
                [LoanStatus.RESERVED, LoanStatus.ACTIVE, LoanStatus.OVERDUE]
            ),
        )
    )
    active_loans = [
        {
            "loan_id": str(loan.loan_id),
            "asset_name": loan.asset.name if loan.asset else None,
            "status": loan.loan_status,
            "borrowed_at": (loan.borrowed_at.isoformat() if loan.borrowed_at else None),
            "due_date": loan.due_date.isoformat() if loan.due_date else None,
        }
        for loan in loans_result.scalars().all()
    ]

    # Fetch audit history
    audit_result = await db.execute(
        select(AuditLog)
        .where(
            or_(
                AuditLog.user_id == user_id,
                AuditLog.payload["target_user_id"].astext == str(user_id),
                AuditLog.payload["user_id"].astext == str(user_id),  # type: ignore[attr-defined]  # backwards-compat with older logs
            )
        )
        .order_by(AuditLog.created_at)
    )
    audit_history = [
        {
            "action_type": log.action_type,
            "payload": log.payload,
            "created_at": (log.created_at.isoformat() if log.created_at else None),
        }
        for log in audit_result.scalars().all()
    ]

    return {
        "user": {
            "user_id": str(user.user_id),
            "first_name": user.first_name,
            "last_name": user.last_name,
            "email": user.email,
            "role_name": user.role.role_name,
            "nfc_tag_id": user.nfc_tag_id,
            "is_active": user.is_active,
            "is_anonymized": user.is_anonymized,
            "accepted_privacy_policy": user.accepted_privacy_policy,
        },
        "active_loans": active_loans,
        "audit_history": audit_history,
    }
