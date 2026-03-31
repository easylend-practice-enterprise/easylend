from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.db.models import LoanStatus

# ---------------------------------------------------------------------------
# Base schema
# ---------------------------------------------------------------------------


class LoanPublicResponse(BaseModel):
    """Loan response WITHOUT user identity — for regular (non-admin) users.

    Excludes user_id to prevent IDOR: regular authenticated users must not
    learn which other users are associated with specific loans.
    """

    model_config = ConfigDict(from_attributes=True, extra="forbid")

    loan_id: UUID
    asset_id: UUID
    checkout_locker_id: UUID
    return_locker_id: UUID | None

    # Server-managed timestamps
    reserved_at: datetime | None
    borrowed_at: datetime | None
    due_date: datetime | None
    returned_at: datetime | None

    loan_status: LoanStatus


class LoanResponse(LoanPublicResponse):
    """Full representation of a loan record returned from the API.

    Includes user_id — for admin users only.
    """

    user_id: UUID  # admin-only field


class LoanListResponse(BaseModel):
    """Paginated list of loans (admin-facing, includes user_id per item)."""

    model_config = ConfigDict(extra="forbid")

    items: list[LoanResponse]
    total: int


class LoanPublicListResponse(BaseModel):
    """Paginated list of loans for regular (non-admin) users — no user_id per item."""

    model_config = ConfigDict(extra="forbid")

    items: list[LoanPublicResponse]
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

    model_config = ConfigDict(extra="forbid")

    aztec_code: str = Field(..., min_length=1, max_length=100)


class ReturnInitiateRequest(BaseModel):
    """Payload sent to start the return flow.

    The backend looks up the active loan for ``loan_id``, finds a free
    locker at the kiosk identified by ``kiosk_id`` (the kiosk where the
    user is currently standing), and begins the return process.
    """

    model_config = ConfigDict(extra="forbid")

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
