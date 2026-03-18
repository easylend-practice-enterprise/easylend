"""
Pydantic schemas for Equipment entities: Category, Kiosk, Locker, and Asset.

Business rules (from docs/architecture.md & docs/erd.mmd):
- Kiosk.kiosk_status  → KioskStatus  enum  (ONLINE | OFFLINE | MAINTENANCE)
- Locker.locker_status → LockerStatus enum  (AVAILABLE | OCCUPIED | MAINTENANCE | ERROR_OPEN)
- Asset.locker_id is *nullable*: NULL when an asset is currently on loan (Dynamic Locker Assignment)
- Asset.asset_status  → AssetStatus  enum  (AVAILABLE | BORROWED | RESERVED |
                                             PENDING_INSPECTION | MAINTENANCE | LOST)
- Asset.is_deleted   → soft-delete flag, server-managed (excluded from Base/Create)
- Assets always belong to exactly one Category (category_id NOT NULL)
"""

from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.db.models import AssetStatus, KioskStatus, LockerStatus

# ---------------------------------------------------------------------------
# CATEGORY
# ---------------------------------------------------------------------------


class CategoryBase(BaseModel):
    """Attributes editable by clients (no server-managed fields)."""

    category_name: str = Field(..., min_length=1, max_length=100)


class CategoryCreate(CategoryBase):
    """No extra fields beyond Base; category_name uniqueness is enforced DB-side."""

    pass


class CategoryUpdate(BaseModel):
    """All fields Optional for PATCH/PUT."""

    category_name: str | None = Field(default=None, min_length=1, max_length=100)


class CategoryResponse(CategoryBase):
    model_config = ConfigDict(from_attributes=True)

    category_id: UUID


class CategoryListResponse(BaseModel):
    items: list[CategoryResponse]
    total: int


# ---------------------------------------------------------------------------
# KIOSK
# ---------------------------------------------------------------------------


class KioskBase(BaseModel):
    """Client-editable kiosk attributes."""

    name: str = Field(..., min_length=1, max_length=100)
    location_description: str = Field(..., min_length=1, max_length=255)
    kiosk_status: KioskStatus = KioskStatus.ONLINE


class KioskCreate(KioskBase):
    """No extra fields; kiosk_status defaults to ONLINE on creation."""

    pass


class KioskUpdate(BaseModel):
    """All fields Optional for PATCH/PUT."""

    name: str | None = Field(default=None, min_length=1, max_length=100)
    location_description: str | None = Field(default=None, min_length=1, max_length=255)
    kiosk_status: KioskStatus | None = None


class KioskStatusUpdate(BaseModel):
    """Schema specifically for the /status endpoint."""

    kiosk_status: KioskStatus


class KioskResponse(KioskBase):
    model_config = ConfigDict(from_attributes=True)

    kiosk_id: UUID


class KioskListResponse(BaseModel):
    items: list[KioskResponse]
    total: int


# ---------------------------------------------------------------------------
# LOCKER
# ---------------------------------------------------------------------------


class LockerBase(BaseModel):
    """Client-editable locker attributes (FK kiosk_id stays in Create/Response)."""

    logical_number: int = Field(..., ge=1)
    locker_status: LockerStatus = LockerStatus.AVAILABLE


class LockerCreate(LockerBase):
    """kiosk_id is required on creation to assign the locker to a physical kiosk."""

    kiosk_id: UUID


class LockerUpdate(BaseModel):
    """All fields Optional for PATCH/PUT.

    Typically only locker_status is changed at runtime (e.g. MAINTENANCE after quarantine).
    kiosk_id may be updated during re-assignment scenarios.
    """

    kiosk_id: UUID | None = None
    logical_number: int | None = Field(default=None, ge=1)
    locker_status: LockerStatus | None = None


class LockerStatusUpdate(BaseModel):
    """Schema specifically for the /status endpoint."""

    locker_status: LockerStatus


class LockerResponse(LockerBase):
    model_config = ConfigDict(from_attributes=True)

    locker_id: UUID
    kiosk_id: UUID


class LockerListResponse(BaseModel):
    items: list[LockerResponse]
    total: int


# ---------------------------------------------------------------------------
# ASSET
# ---------------------------------------------------------------------------


class AssetBase(BaseModel):
    """Client-editable asset attributes.

    Note: locker_id is intentionally excluded here: it is a FK that belongs
    in Create and Response, since it can be NULL (asset on loan).
    """

    name: str = Field(..., min_length=1, max_length=255)
    aztec_code: str = Field(..., min_length=1, max_length=100)
    asset_status: AssetStatus = AssetStatus.AVAILABLE


class AssetCreate(AssetBase):
    """category_id is required; locker_id is optional (asset may be unassigned initially)."""

    category_id: UUID
    locker_id: UUID | None = None


class AssetUpdate(BaseModel):
    """All fields Optional for PATCH/PUT.

    Admins may update any attribute individually, including re-assigning an asset
    to a different category or locker, or marking it LOST / MAINTENANCE.
    is_deleted is intentionally excluded: use the dedicated soft-delete endpoint.
    """

    name: str | None = Field(default=None, min_length=1, max_length=255)
    aztec_code: str | None = Field(default=None, min_length=1, max_length=100)
    asset_status: AssetStatus | None = None
    category_id: UUID | None = None
    locker_id: UUID | None = None


class AssetResponse(AssetBase):
    model_config = ConfigDict(from_attributes=True)

    asset_id: UUID
    category_id: UUID
    locker_id: UUID | None  # NULL when the asset is currently on loan
    is_deleted: bool  # Soft-delete flag; included in responses for admin visibility


class AssetListResponse(BaseModel):
    items: list[AssetResponse]
    total: int
