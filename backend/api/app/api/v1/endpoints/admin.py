"""
Admin quarantine dashboard endpoints: ELP-10 Step 10c.

Router prefix: /admin, tags: ["admin"]

Provides admins with visibility and control over loans that were
quarantined by the Vision AI service (PENDING_INSPECTION).
"""

import logging
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import OperationalError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload, selectinload

from app.api.deps import get_current_user
from app.db.database import get_db
from app.db.models import (
    AIEvaluation,
    Asset,
    AssetStatus,
    EvaluationType,
    Loan,
    LoanStatus,
    Locker,
    LockerStatus,
    User,
)
from app.schemas.admin import (
    EvaluationDetailView,
    QuarantineJudgmentRequest,
    QuarantineLoanView,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin", tags=["admin"])


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _is_lock_not_available_error(exc: OperationalError) -> bool:
    """
    Best-effort detection of a lock-not-available error coming from the DB.
    """
    orig = getattr(exc, "orig", None)
    if orig is None:
        return False
    pgcode = getattr(orig, "pgcode", None) or getattr(orig, "sqlstate", None)
    if pgcode == "55P03":
        return True
    message = str(orig).lower()
    return "database is locked" in message or "lock not available" in message


def _require_admin(current_user: User = Depends(get_current_user)) -> User:
    if current_user.role is None or current_user.role.role_name.upper() != "ADMIN":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Insufficient permissions.",
        )
    return current_user


# ---------------------------------------------------------------------------
# GET /admin/quarantine
# ---------------------------------------------------------------------------


@router.get(
    "/quarantine",
    response_model=list[QuarantineLoanView],
    status_code=status.HTTP_200_OK,
    responses={
        401: {"description": "Not authenticated"},
        403: {"description": "Not an admin"},
    },
)
async def list_quarantine_loans(
    db: AsyncSession = Depends(get_db),
    _: User = Depends(_require_admin),
) -> list[QuarantineLoanView]:
    """
    List all loans in PENDING_INSPECTION status with joined relation names.
    """
    result = await db.execute(
        select(Loan)
        .options(
            joinedload(Loan.asset),
            joinedload(Loan.user),
            joinedload(Loan.checkout_locker).joinedload(Locker.kiosk),
            joinedload(Loan.return_locker).joinedload(Locker.kiosk),
        )
        .where(Loan.loan_status == LoanStatus.PENDING_INSPECTION)
        .order_by(Loan.borrowed_at.desc().nulls_last())
    )
    loans = result.unique().scalars().all()

    views: list[QuarantineLoanView] = []
    for loan in loans:
        asset: Asset = loan.asset  # type: ignore[assignment]
        user: User = loan.user  # type: ignore[assignment]

        # Pick the locker that placed the loan in quarantine
        locker: Locker | None = None
        if loan.return_locker_id is not None:
            locker = loan.return_locker  # type: ignore[assignment]
        elif loan.checkout_locker_id is not None:
            locker = loan.checkout_locker  # type: ignore[assignment]

        kiosk_name = locker.kiosk.name if locker and locker.kiosk else "Unknown"

        views.append(
            QuarantineLoanView(
                loan_id=loan.loan_id,
                asset_name=asset.name if asset else "Unknown",
                user_name=f"{user.first_name} {user.last_name}" if user else "Unknown",
                kiosk_name=kiosk_name,
                reserved_at=loan.reserved_at,
                borrowed_at=loan.borrowed_at,
                returned_at=loan.returned_at,
                loan_status=loan.loan_status,
            )
        )
    return views


# ---------------------------------------------------------------------------
# GET /admin/evaluations/{loan_id}
# ---------------------------------------------------------------------------


@router.get(
    "/evaluations/{loan_id}",
    response_model=EvaluationDetailView,
    status_code=status.HTTP_200_OK,
    responses={
        401: {"description": "Not authenticated"},
        403: {"description": "Not an admin"},
        404: {"description": "Loan or evaluation not found"},
    },
)
async def get_latest_evaluation(
    loan_id: UUID,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(_require_admin),
) -> EvaluationDetailView:
    """
    Return the most recent AI evaluation for a given loan.
    """
    result = await db.execute(
        select(AIEvaluation)
        .where(AIEvaluation.loan_id == loan_id)
        .options(selectinload(AIEvaluation.loan))
        .order_by(AIEvaluation.analyzed_at.desc())
        .limit(1)
    )
    evaluation = result.scalar_one_or_none()

    if evaluation is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No evaluation found for this loan.",
        )

    return EvaluationDetailView.model_validate(evaluation)


# ---------------------------------------------------------------------------
# PATCH /admin/evaluations/{evaluation_id}/judge
# ---------------------------------------------------------------------------


@router.patch(
    "/evaluations/{evaluation_id}/judge",
    status_code=status.HTTP_204_NO_CONTENT,
    responses={
        401: {"description": "Not authenticated"},
        403: {"description": "Not an admin"},
        404: {"description": "Evaluation, loan, asset, or locker not found"},
        409: {"description": "Lock contention"},
    },
)
async def judge_evaluation(
    evaluation_id: UUID,
    judgment: QuarantineJudgmentRequest,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(_require_admin),
) -> None:
    """
    Admin verdict on a quarantined AI evaluation.

    - **is_approved == True** (AI was right): Loan → DISPUTED, Asset → MAINTENANCE.
    - **is_approved == False** (AI was wrong):
        - CHECKOUT eval: Loan → ACTIVE, Asset → BORROWED, Locker → AVAILABLE.
        - RETURN eval: Loan → COMPLETED, Asset → AVAILABLE, Locker → OCCUPIED.
    """
    try:
        eval_result = await db.execute(
            select(AIEvaluation)
            .where(AIEvaluation.evaluation_id == evaluation_id)
            .with_for_update(nowait=True)
        )
    except OperationalError as exc:
        if _is_lock_not_available_error(exc):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Evaluation is currently being processed. Please try again.",
            )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="A database error occurred.",
        ) from exc

    evaluation = eval_result.scalar_one_or_none()
    if evaluation is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Evaluation not found.",
        )

    try:
        loan_result = await db.execute(
            select(Loan)
            .where(Loan.loan_id == evaluation.loan_id)
            .with_for_update(nowait=True)
        )
    except OperationalError as exc:
        if _is_lock_not_available_error(exc):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Loan is currently being processed. Please try again.",
            )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="A database error occurred.",
        ) from exc

    loan = loan_result.scalar_one_or_none()
    if loan is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Loan not found.",
        )

    try:
        asset_result = await db.execute(
            select(Asset)
            .where(Asset.asset_id == loan.asset_id)
            .with_for_update(nowait=True)
        )
    except OperationalError as exc:
        if _is_lock_not_available_error(exc):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Asset is currently being processed. Please try again.",
            )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="A database error occurred.",
        ) from exc

    asset = asset_result.scalar_one_or_none()
    if asset is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Asset not found.",
        )

    locker_id_for_eval = (
        loan.checkout_locker_id
        if evaluation.evaluation_type == EvaluationType.CHECKOUT
        else loan.return_locker_id
    )
    locker: Locker | None = None
    if locker_id_for_eval is not None:
        try:
            locker_result = await db.execute(
                select(Locker)
                .where(Locker.locker_id == locker_id_for_eval)
                .with_for_update(nowait=True)
            )
        except OperationalError as exc:
            if _is_lock_not_available_error(exc):
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="Locker is currently being processed. Please try again.",
                )
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="A database error occurred.",
            ) from exc
        locker = locker_result.scalar_one_or_none()

    # Persist the admin judgment on the evaluation
    evaluation.is_approved = judgment.is_approved
    evaluation.rejection_reason = judgment.rejection_reason

    if judgment.is_approved:
        # AI was right: mark loan as disputed, asset as maintenance
        loan.loan_status = LoanStatus.DISPUTED
        asset.asset_status = AssetStatus.MAINTENANCE
        if locker is not None:
            locker.locker_status = LockerStatus.MAINTENANCE
    else:
        # AI was wrong: revert to normal flow
        if evaluation.evaluation_type == EvaluationType.CHECKOUT:
            loan.loan_status = LoanStatus.ACTIVE
            asset.asset_status = AssetStatus.BORROWED
            if locker is not None:
                locker.locker_status = LockerStatus.AVAILABLE
        else:
            # RETURN evaluation
            from datetime import UTC, datetime

            loan.loan_status = LoanStatus.COMPLETED
            loan.returned_at = datetime.now(UTC)
            asset.asset_status = AssetStatus.AVAILABLE
            if locker is not None:
                locker.locker_status = LockerStatus.OCCUPIED

    await db.commit()
