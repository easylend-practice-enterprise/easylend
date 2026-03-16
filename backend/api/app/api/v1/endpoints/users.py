from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.deps import get_current_admin, get_current_user
from app.core import security
from app.db.database import get_db
from app.db.models import Role, User
from app.schemas.user import UserCreate, UserNfcUpdate, UserResponse, UserUpdate

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


@router.get("/", response_model=list[UserResponse], status_code=status.HTTP_200_OK)
async def list_users(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_admin),
) -> list[User]:
    result = await db.execute(
        select(User).options(selectinload(User.role)).offset(skip).limit(limit)
    )
    return list(result.scalars().all())


@router.get("/me", response_model=UserResponse, status_code=status.HTTP_200_OK)
async def get_me(current_user: User = Depends(get_current_user)) -> User:
    return current_user


@router.get("/{user_id}", response_model=UserResponse, status_code=status.HTTP_200_OK)
async def get_user_by_id(
    user_id: UUID,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_admin),
) -> User:
    return await _get_user_with_role_or_404(db, user_id)


@router.post("/", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def create_user(
    payload: UserCreate,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_admin),
) -> User:
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
        is_active=payload.is_active,
        ban_reason=payload.ban_reason,
    )

    db.add(user)
    await db.commit()

    return await _get_user_with_role_or_404(db, user.user_id)


@router.patch("/{user_id}", response_model=UserResponse, status_code=status.HTTP_200_OK)
async def update_user(
    user_id: UUID,
    payload: UserUpdate,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_admin),
) -> User:
    user = await _get_user_with_role_or_404(db, user_id)

    update_data = payload.model_dump(exclude_unset=True)

    # Voorkom dat niet-nullable kolommen expliciet op None worden gezet
    non_nullable_fields = {"email", "role_id", "first_name", "last_name", "is_active"}
    invalid_null_fields = [
        field for field in non_nullable_fields
        if field in update_data and update_data[field] is None
    ]
    if invalid_null_fields:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Fields {', '.join(sorted(invalid_null_fields))} cannot be null.",
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

    await db.commit()
    return await _get_user_with_role_or_404(db, user_id)


@router.patch(
    "/{user_id}/nfc", response_model=UserResponse, status_code=status.HTTP_200_OK
)
async def update_user_nfc(
    user_id: UUID,
    payload: UserNfcUpdate,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_admin),
) -> User:
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
    await db.commit()
    return await _get_user_with_role_or_404(db, user_id)
