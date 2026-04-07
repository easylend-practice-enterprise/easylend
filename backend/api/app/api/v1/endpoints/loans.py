"""
Loan Transaction endpoints: ELP-28

APIRouter: prefix="/loans", tags=["loans"]

Business rules (Step 10a, hardware-free path):
  - Any authenticated user may list their own loans and poll status.
  - Admins see all loans.
  - Checkout uses SELECT … FOR UPDATE NOWAIT to prevent concurrent
    double-assignment of the same asset (409 on lock contention).
  - Return/initiate uses SELECT … FOR UPDATE SKIP LOCKED to find the
    first available locker at the user's kiosk without blocking peers.
"""

import logging
from datetime import UTC, datetime
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, status
from sqlalchemy import func, select
from sqlalchemy.exc import OperationalError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.deps import get_current_user
from app.core.audit import log_audit_event
from app.core.db_utils import is_lock_not_available_error
from app.core.idempotency import _guard_idempotency, release_idempotency_key
from app.core.rate_limit import check_token_rate_limit
from app.core.state_machine import InvalidLoanTransitionError, LoanStateMachine
from app.core.websockets import manager
from app.db.database import get_db
from app.db.models import (
    Asset,
    AssetStatus,
    Kiosk,
    Loan,
    LoanStatus,
    Locker,
    LockerStatus,
    User,
)
from app.db.redis import (
    redis_client,  # noqa: F401 — test fixtures monkeypatch this name
)
from app.schemas.loan import (
    CheckoutRequest,
    LoanListResponse,
    LoanPublicListResponse,
    LoanPublicResponse,
    LoanResponse,
    LoanStatusResponse,
    ReturnInitiateRequest,
)

logger = logging.getLogger(__name__)


router = APIRouter(prefix="/loans", tags=["loans"])

# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

_PAGINATION_SKIP = Query(0, ge=0, description="Number of records to skip (offset).")
_PAGINATION_LIMIT = Query(
    100, ge=1, le=1000, description="Maximum number of records to return."
)

_IS_ADMIN_ROLE = "ADMIN"


def _is_admin(user: User) -> bool:
    return user.role is not None and user.role.role_name.upper() == _IS_ADMIN_ROLE


async def _get_loan_or_404(db: AsyncSession, loan_id: UUID) -> Loan:
    result = await db.execute(select(Loan).where(Loan.loan_id == loan_id))
    loan = result.scalar_one_or_none()
    if loan is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Loan not found.",
        )
    return loan


# ---------------------------------------------------------------------------
# GET /loans: List loans (paginated, role-scoped)
# ---------------------------------------------------------------------------


@router.get(
    "",
    response_model=LoanListResponse | LoanPublicListResponse,
    status_code=status.HTTP_200_OK,
    responses={
        401: {"description": "Not authenticated"},
    },
)
async def list_loans(
    skip: int = _PAGINATION_SKIP,
    limit: int = _PAGINATION_LIMIT,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> LoanListResponse | LoanPublicListResponse:
    """
    List loans with pagination.

    - **Admin**: all loans in the system.
    - **Any other role**: only the caller's own loans.
    """
    base_query = (
        select(Loan)
        .options(selectinload(Loan.asset))
        .join(Asset, Loan.asset_id == Asset.asset_id)
        .where(Asset.is_deleted.is_(False))
    )
    count_query = (
        select(func.count())
        .select_from(Loan)
        .join(Asset, Loan.asset_id == Asset.asset_id)
        .where(Asset.is_deleted.is_(False))
    )

    if _is_admin(current_user):
        query = base_query
    else:
        query = base_query.where(Loan.user_id == current_user.user_id)
        count_query = count_query.where(Loan.user_id == current_user.user_id)

    result = await db.execute(
        query.order_by(Loan.borrowed_at.desc().nulls_last()).offset(skip).limit(limit)
    )
    loans_list = result.scalars().all()

    total_result = await db.execute(count_query)
    total = total_result.scalar_one_or_none() or 0

    if _is_admin(current_user):
        admin_items = [LoanResponse.model_validate(loan) for loan in loans_list]
        return LoanListResponse(items=admin_items, total=total)
    else:
        public_items = [LoanPublicResponse.model_validate(loan) for loan in loans_list]
        return LoanPublicListResponse(items=public_items, total=total)


# ---------------------------------------------------------------------------
# GET /loans/{loan_id}/status: Fast polling endpoint
# ---------------------------------------------------------------------------


@router.get(
    "/{loan_id}/status",
    response_model=LoanStatusResponse,
    status_code=status.HTTP_200_OK,
    responses={
        401: {"description": "Not authenticated"},
        403: {"description": "Forbidden: not the loan owner"},
        404: {"description": "Loan not found"},
    },
)
async def get_loan_status(
    loan_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> LoanStatusResponse:
    """
    Retrieve the current status of a single loan.

    Intended as a lightweight polling endpoint for the kiosk app.

    - **Admin**: may poll any loan.
    - **Other roles**: may only poll their own loans (returns 403 otherwise).
    """
    loan = await _get_loan_or_404(db, loan_id)

    if not _is_admin(current_user) and loan.user_id != current_user.user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have permission to view this loan.",
        )

    return LoanStatusResponse.model_validate(loan)


# ---------------------------------------------------------------------------
# POST /loans/checkout: Initiate a checkout
# ---------------------------------------------------------------------------


@router.post(
    "/checkout",
    response_model=LoanPublicResponse,
    status_code=status.HTTP_202_ACCEPTED,
    responses={
        400: {"description": "Asset unavailable, not found, or has no locker assigned"},
        401: {"description": "Not authenticated"},
        404: {"description": "Locker not found"},
        409: {"description": "Conflict: lock contention or processing error"},
    },
)
async def checkout(
    request: Request,
    payload: CheckoutRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    idempotency_key: str | None = Header(None, alias="Idempotency-Key"),
) -> LoanPublicResponse:
    """
    Begin a checkout by scanning an asset's Aztec barcode.

    Uses `SELECT … FOR UPDATE NOWAIT` to guarantee that two concurrent
    requests for the same asset cannot both succeed. If the row is already
    locked, a **409 Conflict** is returned immediately (no retry).

    **State transitions (hardware-free path):**
    - `Loan.loan_status`: `RESERVED` (initial status before hardware confirms pickup)
    - `Asset.asset_status`: `AVAILABLE` → `BORROWED`
    - `Asset.locker_id`: unchanged until Vision confirms the checkout result
    - `Locker.locker_status`: unchanged until Vision confirms the locker is empty
    - New `Loan` record created with `loan_status = RESERVED`

    Rate-limited: 60 req/min per authenticated user (Layer 3).
    """
    db_committed = False
    await check_token_rate_limit(request, str(current_user.user_id))
    if not idempotency_key:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Idempotency-Key header is required",
        )

    await _guard_idempotency(idempotency_key)

    try:
        # --- 1. Lock the asset row (NOWAIT: fail fast on contention) ---
        try:
            result = await db.execute(
                select(Asset)
                .where(Asset.aztec_code == payload.aztec_code)
                .with_for_update(nowait=True)
            )
        except OperationalError as exc:
            if is_lock_not_available_error(exc):
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="Asset is currently being processed. Please try again.",
                )
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="A database error occurred.",
            ) from exc

        asset = result.scalar_one_or_none()

        # --- 2. Validate asset ---
        if asset is None or asset.is_deleted:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Asset not found.",
            )

        if asset.asset_status != AssetStatus.AVAILABLE:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Asset is not available for checkout.",
            )

        if asset.locker_id is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Asset has no assigned locker and cannot be checked out.",
            )

        checkout_locker_id: UUID = asset.locker_id

        # --- 3. Lock the locker row so we can safely mutate its status ---
        try:
            locker_result = await db.execute(
                select(Locker)
                .where(Locker.locker_id == checkout_locker_id)
                .with_for_update(nowait=True)
            )
        except OperationalError as exc:
            if is_lock_not_available_error(exc):
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="Locker is currently being processed. Please try again.",
                )
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="A database error occurred.",
            ) from exc
        locker = locker_result.scalar_one_or_none()

        if locker is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Locker not found.",
            )

        # --- 3b. Hardware Pre-flight Check ---
        kiosk_id_str = str(locker.kiosk_id)
        if not await manager.is_kiosk_online(kiosk_id_str):
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="The Vision Box for this locker is currently offline. Cannot checkout.",
            )

        # --- 4. Apply state mutations ---
        # Asset becomes BORROWED immediately; physical locker release is deferred
        # until Vision confirms the checkout outcome.
        asset.asset_status = AssetStatus.BORROWED

        # Validate initial state selection through the centralized state machine.
        try:
            LoanStateMachine.assert_initial_status(LoanStatus.RESERVED)
        except InvalidLoanTransitionError as exc:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Invalid initial loan state configuration.",
            ) from exc

        # --- 5. Create loan record ---
        loan = Loan(
            user_id=current_user.user_id,
            asset_id=asset.asset_id,
            checkout_locker_id=checkout_locker_id,
            loan_status=LoanStatus.RESERVED,
            reserved_at=datetime.now(UTC),
        )
        db.add(loan)
        await db.flush()

        await log_audit_event(
            db,
            action_type="LOAN_CHECKOUT_INITIATED",
            payload={
                "loan_id": str(loan.loan_id),
                "asset_id": str(asset.asset_id),
                "locker_id": str(checkout_locker_id),
                "kiosk_id": str(kiosk_id_str),
            },
            user_id=current_user.user_id,
        )

        # --- 6. Commit DB state BEFORE sending hardware command ---
        # This ensures the loan record is durable. If the hardware command
        # fails after commit, the DB is consistent and the RESERVED loan will
        # be cleaned up by the timeout worker.
        await db.commit()
        db_committed = True
        await db.refresh(loan)

        # --- 7. Trigger Hardware to open the door ---
        command_ok = await manager.send_command(
            kiosk_id_str,
            {
                "action": "open_slot",
                "locker_id": str(locker.logical_number),
                "loan_id": str(loan.loan_id),
                "evaluation_type": "CHECKOUT",
            },
        )
        if not command_ok:
            # DB is committed (loan is RESERVED); hardware failed.
            # The timeout worker will eventually clean this up.
            # Log the inconsistency so ops can detect it.
            logger.warning(
                "Hardware command failed after DB commit for checkout loan=%s.",
                loan.loan_id,
            )
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Unable to initiate checkout: kiosk hardware unavailable. Please try again.",
            )

        return LoanPublicResponse.model_validate(loan)
    except HTTPException:
        # Re-raise HTTPExceptions directly so FastAPI formats them correctly
        if not db_committed:
            await release_idempotency_key(idempotency_key)
        raise
    except Exception:
        try:
            await db.rollback()
        except Exception:
            logger.exception("Failed to rollback DB during error handling.")
        await release_idempotency_key(idempotency_key)
        raise


# ---------------------------------------------------------------------------
# POST /loans/return/initiate: Begin the return flow
# ---------------------------------------------------------------------------


@router.post(
    "/return/initiate",
    response_model=LoanPublicResponse,
    status_code=status.HTTP_202_ACCEPTED,
    responses={
        400: {"description": "Loan is not in ACTIVE state"},
        401: {"description": "Not authenticated"},
        403: {"description": "Forbidden: not the loan owner"},
        404: {"description": "Loan or Kiosk not found"},
        409: {"description": "Conflict: loan state changed or lock contention"},
        503: {"description": "No available lockers at the requested kiosk"},
    },
)
async def return_initiate(
    request: Request,
    payload: ReturnInitiateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    idempotency_key: str | None = Header(None, alias="Idempotency-Key"),
) -> LoanPublicResponse:
    """
    Initiate the return process for an active loan.

    Finds the first available locker at the kiosk where the user is
    standing (`payload.kiosk_id`) using `SELECT … FOR UPDATE SKIP LOCKED`
    so that concurrent return requests from different users never grab the
    same slot.

    **State transitions:**
    - `Locker.locker_status`: `AVAILABLE` → `OCCUPIED` (reserved for this return)
    - `Loan.return_locker_id`: assigned to the chosen locker
    - `Loan.loan_status`: `ACTIVE` → `RETURNING`

    Rate-limited: 60 req/min per authenticated user (Layer 3).
    """
    db_committed = False
    await check_token_rate_limit(request, str(current_user.user_id))
    if not idempotency_key:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Idempotency-Key header is required",
        )

    await _guard_idempotency(idempotency_key)

    try:
        # --- 0. Validate that the kiosk exists (BEFORE hardware check) ---
        kiosk_result = await db.execute(
            select(Kiosk).where(Kiosk.kiosk_id == payload.kiosk_id)
        )
        kiosk = kiosk_result.scalar_one_or_none()
        if kiosk is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Kiosk not found.",
            )

        # --- 0b. Hardware Pre-flight Check ---
        kiosk_id_str = str(payload.kiosk_id)
        if not await manager.is_kiosk_online(kiosk_id_str):
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="The chosen Vision Box is currently offline. Cannot return here.",
            )

        # --- 1. Fetch and validate the loan (non-locking) ---
        loan = await _get_loan_or_404(db, payload.loan_id)

        if not _is_admin(current_user) and loan.user_id != current_user.user_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You do not have permission to return this loan.",
            )

        if loan.loan_status != LoanStatus.ACTIVE:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Loan is not active and cannot be returned.",
            )

        # --- 1b. Lock the loan row and enforce atomic state transition ---
        try:
            locked_loan_result = await db.execute(
                select(Loan)
                .where(
                    Loan.loan_id == payload.loan_id,
                    Loan.loan_status == LoanStatus.ACTIVE,
                    Loan.return_locker_id.is_(None),
                )
                .with_for_update(nowait=True)
            )
        except OperationalError as exc:
            if is_lock_not_available_error(exc):
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="A return is already in progress for this loan. Please try again shortly.",
                )
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="A database error occurred.",
            ) from exc

        locked_loan = locked_loan_result.scalar_one_or_none()
        if locked_loan is None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Loan is no longer in a state that can be returned.",
            )
        loan = locked_loan

        # --- 2. Find and lock a free locker at this kiosk (SKIP LOCKED + FOR UPDATE) ---
        # SKIP LOCKED prevents blocking on other return requests.
        # FOR UPDATE ensures the selected row is locked: no two concurrent
        # requests can both select the same locker even with SKIP LOCKED.
        try:
            locker_result = await db.execute(
                select(Locker)
                .where(
                    Locker.kiosk_id == payload.kiosk_id,
                    Locker.locker_status == LockerStatus.AVAILABLE,
                )
                .order_by(Locker.logical_number)
                .limit(1)
                .with_for_update(skip_locked=True)
            )
        except OperationalError as exc:
            if is_lock_not_available_error(exc):
                raise HTTPException(
                    status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                    detail="No available lockers at this kiosk. Please try again shortly.",
                )
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="A database error occurred.",
            ) from exc
        locker = locker_result.scalar_one_or_none()

        if locker is None:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="No available lockers at this kiosk. Please try again shortly.",
            )

        # --- 3. Reserve the locker and update the loan ---
        try:
            transition = LoanStateMachine.transition(
                loan.loan_status,
                LoanStatus.RETURNING,
            )
        except InvalidLoanTransitionError as exc:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=str(exc),
            ) from exc

        if transition.locker_status is not None:
            locker.locker_status = transition.locker_status
        loan.return_locker_id = locker.locker_id
        loan.loan_status = transition.loan_status

        await log_audit_event(
            db,
            action_type="LOAN_RETURN_INITIATED",
            payload={
                "loan_id": str(loan.loan_id),
                "asset_id": str(loan.asset_id),
                "return_locker_id": str(locker.locker_id),
                "kiosk_id": str(kiosk_id_str),
            },
            user_id=current_user.user_id,
        )

        # --- 4. Commit DB state BEFORE sending hardware command ---
        # This ensures the loan record is durable. If the hardware command
        # fails after commit, the DB is consistent and the RETURNING loan will
        # be cleaned up by the timeout worker.
        await db.commit()
        db_committed = True
        await db.refresh(loan)

        # --- 5. Trigger Hardware to open the door ---
        command_ok = await manager.send_command(
            kiosk_id_str,
            {
                "action": "open_slot",
                "locker_id": str(locker.logical_number),
                "loan_id": str(loan.loan_id),
                "evaluation_type": "RETURN",
            },
        )
        if not command_ok:
            # DB is committed (loan is RETURNING); hardware failed.
            # The timeout worker will eventually clean this up.
            logger.warning(
                "Hardware command failed after DB commit for return loan=%s.",
                loan.loan_id,
            )
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Unable to initiate return: kiosk hardware unavailable. Please try again.",
            )

        return LoanPublicResponse.model_validate(loan)
    except HTTPException:
        # Re-raise HTTPExceptions directly so FastAPI formats them correctly
        if not db_committed:
            await release_idempotency_key(idempotency_key)
        raise
    except Exception:
        try:
            await db.rollback()
        except Exception:
            logger.exception("Failed to rollback DB during error handling.")
        await release_idempotency_key(idempotency_key)
        raise
