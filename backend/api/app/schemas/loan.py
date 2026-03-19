from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.db.models import LoanStatus

# ---------------------------------------------------------------------------
# Base schema
# ---------------------------------------------------------------------------


class LoanBase(BaseModel):
    """Core loan fields shared by loan response schemas.

    These fields are populated and managed by server-side business logic,
    not supplied by callers. Server-managed timestamps (reserved_at,
    borrowed_at, due_date, returned_at) and FK identifiers resolved by
    business logic are intentionally excluded here.
    """

    user_id: UUID
    asset_id: UUID
    checkout_locker_id: UUID


# ---------------------------------------------------------------------------
# Response schemas
# ---------------------------------------------------------------------------


class LoanResponse(LoanBase):
    """Full representation of a loan record returned from the API."""

    model_config = ConfigDict(from_attributes=True)

    loan_id: UUID
    return_locker_id: UUID | None

    # Server-managed timestamps
    reserved_at: datetime | None
    borrowed_at: datetime | None
    due_date: datetime | None
    returned_at: datetime | None

    loan_status: LoanStatus


class LoanListResponse(BaseModel):
    """Paginated list of loans."""

    items: list[LoanResponse]
    total: int


# ---------------------------------------------------------------------------
# Request schemas
# ---------------------------------------------------------------------------


class CheckoutRequest(BaseModel):
    """Payload the kiosk sends to initiate a checkout.

    The ``aztec_code`` is the barcode scanned from the asset label on the
    kiosk screen. The backend resolves the associated asset, uses that
    asset's current locker to lock the asset/locker, creates the loan
    record, and then frees the locker.
    """

    aztec_code: str = Field(..., min_length=1, max_length=100)


class ReturnInitiateRequest(BaseModel):
    """Payload sent to start the return flow.

    The backend looks up the active loan for ``loan_id``, finds a free
    locker at the kiosk identified by ``kiosk_id`` (the kiosk where the
    user is currently standing), and begins the return process.
    """

    loan_id: UUID
    kiosk_id: UUID


# ---------------------------------------------------------------------------
# Polling schema
# ---------------------------------------------------------------------------


class LoanStatusResponse(BaseModel):
    """Minimal payload for the status-polling endpoint.

    The kiosk polls ``GET /api/v1/loans/{loan_id}/status`` until the
    ``loan_status`` reaches the desired state for the kiosk flow (for
    example, a final state such as ``COMPLETED`` or ``FRAUD_SUSPECTED``).
    """

    model_config = ConfigDict(from_attributes=True)

    loan_id: UUID
    loan_status: LoanStatus
