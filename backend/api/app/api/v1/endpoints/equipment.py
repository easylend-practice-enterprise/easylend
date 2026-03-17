"""
Equipment CRUD endpoints — ELP-26

Four APIRouters, one per entity, in dependency order:
    categories_router  → /categories
    kiosks_router      → /kiosks
    lockers_router     → /lockers
    assets_router      → /assets

Auth rules:
  - All write operations (POST / PATCH / PUT / DELETE) require Admin.
  - Admin-only GET list endpoints are also guarded.
  - GET /categories and GET /assets (+ /assets/{id}) are readable by
    every authenticated user (student / medewerker / admin) so the
    catalog flow and the kiosk-checkout flow can function without
    elevated privileges.
"""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_admin, get_current_user
from app.db.database import get_db
from app.db.models import Asset, AssetStatus, Category, Kiosk, Locker, User
from app.schemas.equipment import (
    AssetCreate,
    AssetListResponse,
    AssetResponse,
    AssetUpdate,
    CategoryCreate,
    CategoryListResponse,
    CategoryResponse,
    CategoryUpdate,
    KioskCreate,
    KioskListResponse,
    KioskResponse,
    KioskUpdate,
    LockerCreate,
    LockerListResponse,
    LockerResponse,
    LockerUpdate,
)

# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

_PAGINATION_SKIP = Query(0, ge=0, description="Number of records to skip (offset).")
_PAGINATION_LIMIT = Query(
    100, ge=1, le=1000, description="Maximum number of records to return."
)


# ---------------------------------------------------------------------------
# CATEGORIES
# ---------------------------------------------------------------------------

categories_router = APIRouter(prefix="/categories", tags=["categories"])


async def _get_category_or_404(db: AsyncSession, category_id: UUID) -> Category:
    result = await db.execute(
        select(Category).where(Category.category_id == category_id)
    )
    category = result.scalar_one_or_none()
    if category is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Category not found.",
        )
    return category


@categories_router.get(
    "",
    response_model=CategoryListResponse,
    status_code=status.HTTP_200_OK,
    responses={
        401: {"description": "Not authenticated"},
    },
)
async def list_categories(
    skip: int = _PAGINATION_SKIP,
    limit: int = _PAGINATION_LIMIT,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
) -> CategoryListResponse:
    """
    List all asset categories with pagination.

    Accessible by every authenticated user (student, medewerker, admin).
    Used by the kiosk catalog view to group available assets.
    """
    result = await db.execute(
        select(Category).order_by(Category.category_name).offset(skip).limit(limit)
    )
    items = [CategoryResponse.model_validate(c) for c in result.scalars().all()]

    total_result = await db.execute(select(func.count()).select_from(Category))
    total = total_result.scalar_one_or_none() or 0

    return CategoryListResponse(items=items, total=total)


@categories_router.post(
    "",
    response_model=CategoryResponse,
    status_code=status.HTTP_201_CREATED,
    responses={
        400: {"description": "Category name already exists"},
        401: {"description": "Not authenticated"},
        403: {"description": "Forbidden – Admin only"},
    },
)
async def create_category(
    payload: CategoryCreate,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_admin),
) -> CategoryResponse:
    """
    Create a new asset category.

    Requires Admin role. `category_name` must be unique (DB constraint).
    """
    category = Category(category_name=payload.category_name)
    db.add(category)
    try:
        await db.commit()
        await db.refresh(category)
    except IntegrityError:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Category name already exists.",
        )
    return CategoryResponse.model_validate(category)


@categories_router.put(
    "/{category_id}",
    response_model=CategoryResponse,
    status_code=status.HTTP_200_OK,
    responses={
        400: {"description": "Category name already exists"},
        401: {"description": "Not authenticated"},
        403: {"description": "Forbidden – Admin only"},
        404: {"description": "Category not found"},
    },
)
@categories_router.patch(
    "/{category_id}",
    response_model=CategoryResponse,
    status_code=status.HTTP_200_OK,
    include_in_schema=False,  # Surface only PUT in Swagger; PATCH shares handler
)
async def update_category(
    category_id: UUID,
    payload: CategoryUpdate,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_admin),
) -> CategoryResponse:
    """
    Update an existing category (full or partial).

    Requires Admin role. Both `PUT` and `PATCH` are accepted; all fields
    in the request body are optional so partial updates are supported.
    """
    category = await _get_category_or_404(db, category_id)

    update_data = payload.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(category, field, value)

    try:
        await db.commit()
        await db.refresh(category)
    except IntegrityError:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Category name already exists.",
        )
    return CategoryResponse.model_validate(category)


# ---------------------------------------------------------------------------
# KIOSKS
# ---------------------------------------------------------------------------

kiosks_router = APIRouter(prefix="/kiosks", tags=["kiosks"])


async def _get_kiosk_or_404(db: AsyncSession, kiosk_id: UUID) -> Kiosk:
    result = await db.execute(select(Kiosk).where(Kiosk.kiosk_id == kiosk_id))
    kiosk = result.scalar_one_or_none()
    if kiosk is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Kiosk not found.",
        )
    return kiosk


@kiosks_router.get(
    "",
    response_model=KioskListResponse,
    status_code=status.HTTP_200_OK,
    responses={
        401: {"description": "Not authenticated"},
        403: {"description": "Forbidden – Admin only"},
    },
)
async def list_kiosks(
    skip: int = _PAGINATION_SKIP,
    limit: int = _PAGINATION_LIMIT,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_admin),
) -> KioskListResponse:
    """
    List all registered kiosk devices with pagination.

    Requires Admin role.
    """
    result = await db.execute(
        select(Kiosk).order_by(Kiosk.name).offset(skip).limit(limit)
    )
    items = [KioskResponse.model_validate(k) for k in result.scalars().all()]

    total_result = await db.execute(select(func.count()).select_from(Kiosk))
    total = total_result.scalar_one_or_none() or 0

    return KioskListResponse(items=items, total=total)


@kiosks_router.post(
    "",
    response_model=KioskResponse,
    status_code=status.HTTP_201_CREATED,
    responses={
        401: {"description": "Not authenticated"},
        403: {"description": "Forbidden – Admin only"},
    },
)
async def create_kiosk(
    payload: KioskCreate,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_admin),
) -> KioskResponse:
    """
    Register a new kiosk device.

    Requires Admin role. Status defaults to `ONLINE` unless explicitly
    set otherwise in the request body.
    """
    kiosk = Kiosk(
        name=payload.name,
        location_description=payload.location_description,
        kiosk_status=payload.kiosk_status,
    )
    db.add(kiosk)
    await db.commit()
    await db.refresh(kiosk)
    return KioskResponse.model_validate(kiosk)


@kiosks_router.put(
    "/{kiosk_id}/status",
    response_model=KioskResponse,
    status_code=status.HTTP_200_OK,
    responses={
        401: {"description": "Not authenticated"},
        403: {"description": "Forbidden – Admin only"},
        404: {"description": "Kiosk not found"},
    },
)
@kiosks_router.patch(
    "/{kiosk_id}/status",
    response_model=KioskResponse,
    status_code=status.HTTP_200_OK,
    include_in_schema=False,
)
async def update_kiosk(
    kiosk_id: UUID,
    payload: KioskUpdate,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_admin),
) -> KioskResponse:
    """
    Update a kiosk's metadata or operational status.

    Requires Admin role. Typically used to change `kiosk_status`
    (e.g. `ONLINE` → `MAINTENANCE`) via the Admin Remote Control flow.
    All fields are optional so partial updates are supported.
    """
    kiosk = await _get_kiosk_or_404(db, kiosk_id)

    update_data = payload.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(kiosk, field, value)

    await db.commit()
    await db.refresh(kiosk)
    return KioskResponse.model_validate(kiosk)


# ---------------------------------------------------------------------------
# LOCKERS
# ---------------------------------------------------------------------------

lockers_router = APIRouter(prefix="/lockers", tags=["lockers"])


async def _get_locker_or_404(db: AsyncSession, locker_id: UUID) -> Locker:
    result = await db.execute(select(Locker).where(Locker.locker_id == locker_id))
    locker = result.scalar_one_or_none()
    if locker is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Locker not found.",
        )
    return locker


@lockers_router.get(
    "",
    response_model=LockerListResponse,
    status_code=status.HTTP_200_OK,
    responses={
        401: {"description": "Not authenticated"},
        403: {"description": "Forbidden – Admin only"},
    },
)
async def list_lockers(
    skip: int = _PAGINATION_SKIP,
    limit: int = _PAGINATION_LIMIT,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_admin),
) -> LockerListResponse:
    """
    List all lockers across all kiosks with pagination.

    Requires Admin role.
    """
    result = await db.execute(
        select(Locker)
        .order_by(Locker.kiosk_id, Locker.logical_number)
        .offset(skip)
        .limit(limit)
    )
    items = [LockerResponse.model_validate(lo) for lo in result.scalars().all()]

    total_result = await db.execute(select(func.count()).select_from(Locker))
    total = total_result.scalar_one_or_none() or 0

    return LockerListResponse(items=items, total=total)


@lockers_router.get(
    "/{locker_id}",
    response_model=LockerResponse,
    status_code=status.HTTP_200_OK,
    responses={
        401: {"description": "Not authenticated"},
        403: {"description": "Forbidden – Admin only"},
        404: {"description": "Locker not found"},
    },
)
async def get_locker_by_id(
    locker_id: UUID,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_admin),
) -> LockerResponse:
    """
    Retrieve a single locker by its unique identifier.

    Requires Admin role.
    """
    locker = await _get_locker_or_404(db, locker_id)
    return LockerResponse.model_validate(locker)


@lockers_router.post(
    "",
    response_model=LockerResponse,
    status_code=status.HTTP_201_CREATED,
    responses={
        400: {"description": "Invalid kiosk_id or duplicate logical_number"},
        401: {"description": "Not authenticated"},
        403: {"description": "Forbidden – Admin only"},
    },
)
async def create_locker(
    payload: LockerCreate,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_admin),
) -> LockerResponse:
    """
    Add a new locker to an existing kiosk.

    Requires Admin role. `kiosk_id` must reference an existing kiosk.
    `logical_number` is the physical slot label (1, 2, 3 …) and must be
    unique within the kiosk.
    """
    kiosk_exists = await db.execute(
        select(Kiosk.kiosk_id).where(Kiosk.kiosk_id == payload.kiosk_id)
    )
    if kiosk_exists.scalar_one_or_none() is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid kiosk_id: kiosk does not exist.",
        )

    locker = Locker(
        kiosk_id=payload.kiosk_id,
        logical_number=payload.logical_number,
        locker_status=payload.locker_status,
    )
    db.add(locker)
    try:
        await db.commit()
        await db.refresh(locker)
    except IntegrityError:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="A locker with this logical_number already exists for this kiosk.",
        )
    return LockerResponse.model_validate(locker)


@lockers_router.patch(
    "/{locker_id}/status",
    response_model=LockerResponse,
    status_code=status.HTTP_200_OK,
    responses={
        400: {"description": "Invalid kiosk_id"},
        401: {"description": "Not authenticated"},
        403: {"description": "Forbidden – Admin only"},
        404: {"description": "Locker not found"},
    },
)
async def update_locker_status(
    locker_id: UUID,
    payload: LockerUpdate,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_admin),
) -> LockerResponse:
    """
    Update a locker's status (and optionally other attributes).

    Requires Admin role. Primarily used by the Quarantine flow to set
    `locker_status = MAINTENANCE` when a damage inspection is pending,
    or to restore a locker to `AVAILABLE` after an admin resolves it.

    All fields in the payload are optional.
    """
    locker = await _get_locker_or_404(db, locker_id)

    update_data = payload.model_dump(exclude_unset=True)

    if "kiosk_id" in update_data and update_data["kiosk_id"] is not None:
        kiosk_exists = await db.execute(
            select(Kiosk.kiosk_id).where(Kiosk.kiosk_id == update_data["kiosk_id"])
        )
        if kiosk_exists.scalar_one_or_none() is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid kiosk_id: kiosk does not exist.",
            )

    for field, value in update_data.items():
        setattr(locker, field, value)

    await db.commit()
    await db.refresh(locker)
    return LockerResponse.model_validate(locker)


# ---------------------------------------------------------------------------
# ASSETS
# ---------------------------------------------------------------------------

assets_router = APIRouter(prefix="/assets", tags=["assets"])


async def _get_asset_or_404(db: AsyncSession, asset_id: UUID) -> Asset:
    result = await db.execute(select(Asset).where(Asset.asset_id == asset_id))
    asset = result.scalar_one_or_none()
    if asset is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Asset not found.",
        )
    return asset


@assets_router.get(
    "",
    response_model=AssetListResponse,
    status_code=status.HTTP_200_OK,
    responses={
        401: {"description": "Not authenticated"},
    },
)
async def list_assets(
    skip: int = _PAGINATION_SKIP,
    limit: int = _PAGINATION_LIMIT,
    asset_status: AssetStatus | None = Query(
        None,
        description=(
            "Optional filter. Only return assets with this status. "
            "Possible values: AVAILABLE, BORROWED, RESERVED, "
            "PENDING_INSPECTION, MAINTENANCE, LOST."
        ),
    ),
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
) -> AssetListResponse:
    """
    List assets with pagination and an optional status filter.

    Accessible by every authenticated user. Soft-deleted assets
    (`is_deleted = True`) are always excluded from this listing so
    that the catalog never surfaces retired equipment.

    Use the `asset_status` query parameter to narrow results:
    - Kiosk app catalog view: `?asset_status=AVAILABLE`
    - Admin overview: omit the filter to see everything active.
    """
    query = select(Asset).where(Asset.is_deleted.is_(False))
    count_query = (
        select(func.count()).select_from(Asset).where(Asset.is_deleted.is_(False))
    )

    if asset_status is not None:
        query = query.where(Asset.asset_status == asset_status)
        count_query = count_query.where(Asset.asset_status == asset_status)

    result = await db.execute(query.order_by(Asset.name).offset(skip).limit(limit))
    items = [AssetResponse.model_validate(a) for a in result.scalars().all()]

    total_result = await db.execute(count_query)
    total = total_result.scalar_one_or_none() or 0

    return AssetListResponse(items=items, total=total)


@assets_router.get(
    "/{asset_id}",
    response_model=AssetResponse,
    status_code=status.HTTP_200_OK,
    responses={
        401: {"description": "Not authenticated"},
        404: {"description": "Asset not found"},
    },
)
async def get_asset_by_id(
    asset_id: UUID,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
) -> AssetResponse:
    """
    Retrieve a single asset by its unique identifier.

    Accessible by every authenticated user. Returns the asset regardless
    of `is_deleted` status so that admins performing a GET by ID (e.g.
    from a loan history) can still fetch the record.
    """
    asset = await _get_asset_or_404(db, asset_id)
    return AssetResponse.model_validate(asset)


@assets_router.post(
    "",
    response_model=AssetResponse,
    status_code=status.HTTP_201_CREATED,
    responses={
        400: {
            "description": "Duplicate aztec_code, invalid category_id, or invalid locker_id"
        },
        401: {"description": "Not authenticated"},
        403: {"description": "Forbidden – Admin only"},
    },
)
async def create_asset(
    payload: AssetCreate,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_admin),
) -> AssetResponse:
    """
    Register a new physical asset in the system.

    Requires Admin role.

    - `aztec_code` must be unique (matches the barcode printed on the item).
    - `category_id` must reference an existing category.
    - `locker_id` is optional; omit it if the asset is not yet physically
      placed in a locker (e.g. asset is being prepared).
    """
    category_exists = await db.execute(
        select(Category.category_id).where(Category.category_id == payload.category_id)
    )
    if category_exists.scalar_one_or_none() is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid category_id: category does not exist.",
        )

    if payload.locker_id is not None:
        locker_exists = await db.execute(
            select(Locker.locker_id).where(Locker.locker_id == payload.locker_id)
        )
        if locker_exists.scalar_one_or_none() is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid locker_id: locker does not exist.",
            )

    asset = Asset(
        category_id=payload.category_id,
        locker_id=payload.locker_id,
        name=payload.name,
        aztec_code=payload.aztec_code,
        asset_status=payload.asset_status,
    )
    db.add(asset)
    try:
        await db.commit()
        await db.refresh(asset)
    except IntegrityError:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="An asset with this aztec_code already exists.",
        )
    return AssetResponse.model_validate(asset)


@assets_router.put(
    "/{asset_id}",
    response_model=AssetResponse,
    status_code=status.HTTP_200_OK,
    responses={
        400: {
            "description": "Duplicate aztec_code, invalid category_id, or invalid locker_id"
        },
        401: {"description": "Not authenticated"},
        403: {"description": "Forbidden – Admin only"},
        404: {"description": "Asset not found"},
    },
)
@assets_router.patch(
    "/{asset_id}",
    response_model=AssetResponse,
    status_code=status.HTTP_200_OK,
    include_in_schema=False,
)
async def update_asset(
    asset_id: UUID,
    payload: AssetUpdate,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_admin),
) -> AssetResponse:
    """
    Update an existing asset (full or partial).

    Requires Admin role. Both `PUT` and `PATCH` are accepted; all fields
    in `AssetUpdate` are optional so partial updates are supported.

    Common admin use-cases:
    - Mark an asset `MAINTENANCE` or `LOST` via `asset_status`.
    - Re-assign an asset to a different category or locker.
    - Correct a typo in `name` or `aztec_code`.

    `is_deleted` is deliberately **not** updatable here — use the
    dedicated `DELETE /{asset_id}` endpoint for soft-deletion.
    """
    asset = await _get_asset_or_404(db, asset_id)

    update_data = payload.model_dump(exclude_unset=True)

    if "category_id" in update_data and update_data["category_id"] is not None:
        cat_exists = await db.execute(
            select(Category.category_id).where(
                Category.category_id == update_data["category_id"]
            )
        )
        if cat_exists.scalar_one_or_none() is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid category_id: category does not exist.",
            )

    if "locker_id" in update_data and update_data["locker_id"] is not None:
        loc_exists = await db.execute(
            select(Locker.locker_id).where(Locker.locker_id == update_data["locker_id"])
        )
        if loc_exists.scalar_one_or_none() is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid locker_id: locker does not exist.",
            )

    for field, value in update_data.items():
        setattr(asset, field, value)

    try:
        await db.commit()
        await db.refresh(asset)
    except IntegrityError:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="An asset with this aztec_code already exists.",
        )
    return AssetResponse.model_validate(asset)


@assets_router.delete(
    "/{asset_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    responses={
        401: {"description": "Not authenticated"},
        403: {"description": "Forbidden – Admin only"},
        404: {"description": "Asset not found"},
    },
)
async def soft_delete_asset(
    asset_id: UUID,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_admin),
) -> None:
    """
    Soft-delete an asset (sets `is_deleted = True`).

    Requires Admin role. The record is **not** physically removed; all
    historical loan records and AI evaluations that reference this asset
    remain intact. The asset is hidden from the `GET /assets` listing
    immediately after deletion.

    `asset_status` is intentionally preserved as-is so that audit logs
    and in-flight loans are not silently corrupted.
    """
    asset = await _get_asset_or_404(db, asset_id)
    asset.is_deleted = True
    await db.commit()
