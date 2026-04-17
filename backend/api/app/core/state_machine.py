"""Domain state machine for loan lifecycle transitions.

Centralizes legal loan status transitions and the coupled asset/locker
status outcomes that keep transaction state synchronized.
"""

from dataclasses import dataclass
from typing import Any

from app.db.models import AssetStatus, LoanStatus, LockerStatus


class InvalidLoanTransitionError(ValueError):
    """Raised when a requested loan status transition is illegal."""


@dataclass(frozen=True)
class LoanTransitionOutcome:
    """Represents the canonical synchronized status outcome for a transition."""

    loan_status: LoanStatus
    asset_status: AssetStatus | None = None
    locker_status: LockerStatus | None = None
    suspend_users: bool = False


class LoanStateMachine:
    """Validates and resolves legal loan transitions."""

    _INITIAL_STATUSES = {LoanStatus.RESERVED}

    _TRANSITIONS: dict[
        tuple[LoanStatus | None, LoanStatus],
        LoanTransitionOutcome,
    ] = {
        # Initial checkout reservation path
        (None, LoanStatus.RESERVED): LoanTransitionOutcome(
            loan_status=LoanStatus.RESERVED,
            asset_status=AssetStatus.BORROWED,
        ),
        # Checkout path
        (LoanStatus.RESERVED, LoanStatus.ACTIVE): LoanTransitionOutcome(
            loan_status=LoanStatus.ACTIVE,
            asset_status=AssetStatus.BORROWED,
            locker_status=LockerStatus.AVAILABLE,
        ),
        (LoanStatus.RESERVED, LoanStatus.FRAUD_SUSPECTED): LoanTransitionOutcome(
            loan_status=LoanStatus.FRAUD_SUSPECTED,
            asset_status=AssetStatus.AVAILABLE,
            locker_status=LockerStatus.OCCUPIED,
        ),
        (LoanStatus.RESERVED, LoanStatus.PENDING_INSPECTION): LoanTransitionOutcome(
            loan_status=LoanStatus.PENDING_INSPECTION,
            asset_status=AssetStatus.PENDING_INSPECTION,
            locker_status=LockerStatus.MAINTENANCE,
        ),
        # Return initiation
        (LoanStatus.ACTIVE, LoanStatus.RETURNING): LoanTransitionOutcome(
            loan_status=LoanStatus.RETURNING,
            locker_status=LockerStatus.OCCUPIED,
        ),
        # Return evaluation path
        (LoanStatus.RETURNING, LoanStatus.COMPLETED): LoanTransitionOutcome(
            loan_status=LoanStatus.COMPLETED,
            asset_status=AssetStatus.AVAILABLE,
            locker_status=LockerStatus.OCCUPIED,
        ),
        (LoanStatus.RETURNING, LoanStatus.FRAUD_SUSPECTED): LoanTransitionOutcome(
            loan_status=LoanStatus.FRAUD_SUSPECTED,
            asset_status=AssetStatus.PENDING_INSPECTION,
            locker_status=LockerStatus.MAINTENANCE,
        ),
        (LoanStatus.RETURNING, LoanStatus.PENDING_INSPECTION): LoanTransitionOutcome(
            loan_status=LoanStatus.PENDING_INSPECTION,
            asset_status=AssetStatus.PENDING_INSPECTION,
            locker_status=LockerStatus.MAINTENANCE,
        ),
        # Additional explicit pathways used outside callbacks/workers
        (LoanStatus.ACTIVE, LoanStatus.OVERDUE): LoanTransitionOutcome(
            loan_status=LoanStatus.OVERDUE,
            asset_status=AssetStatus.BORROWED,
        ),
        (LoanStatus.ACTIVE, LoanStatus.DISPUTED): LoanTransitionOutcome(
            loan_status=LoanStatus.DISPUTED,
            asset_status=AssetStatus.MAINTENANCE,
            locker_status=LockerStatus.MAINTENANCE,
            suspend_users=True,
        ),
        (LoanStatus.FRAUD_SUSPECTED, LoanStatus.DISPUTED): LoanTransitionOutcome(
            loan_status=LoanStatus.DISPUTED,
            asset_status=AssetStatus.MAINTENANCE,
            locker_status=LockerStatus.MAINTENANCE,
            suspend_users=True,
        ),
        (LoanStatus.PENDING_INSPECTION, LoanStatus.DISPUTED): LoanTransitionOutcome(
            loan_status=LoanStatus.DISPUTED,
            asset_status=AssetStatus.MAINTENANCE,
            locker_status=LockerStatus.MAINTENANCE,
        ),
        (LoanStatus.PENDING_INSPECTION, LoanStatus.ACTIVE): LoanTransitionOutcome(
            loan_status=LoanStatus.ACTIVE,
            asset_status=AssetStatus.BORROWED,
            locker_status=LockerStatus.AVAILABLE,
        ),
        (LoanStatus.PENDING_INSPECTION, LoanStatus.COMPLETED): LoanTransitionOutcome(
            loan_status=LoanStatus.COMPLETED,
            asset_status=AssetStatus.AVAILABLE,
            locker_status=LockerStatus.OCCUPIED,
        ),
    }

    @classmethod
    def assert_initial_status(cls, initial_status: LoanStatus) -> None:
        if initial_status not in cls._INITIAL_STATUSES:
            allowed = ", ".join(status.value for status in cls._INITIAL_STATUSES)
            raise InvalidLoanTransitionError(
                f"Illegal initial loan status: {initial_status.value}. Allowed: {allowed}."
            )

    @classmethod
    def transition(
        cls,
        current_status: LoanStatus | None,
        desired_status: LoanStatus,
    ) -> LoanTransitionOutcome:
        outcome = cls._TRANSITIONS.get((current_status, desired_status))
        if outcome is None:
            current_label = (
                current_status.value if current_status is not None else "None"
            )
            raise InvalidLoanTransitionError(
                f"Illegal loan transition: {current_label} -> {desired_status.value}."
            )
        return outcome

    @classmethod
    def apply_transition(
        cls,
        loan: Any,
        asset: Any | None,
        locker: Any | None,
        target_status: LoanStatus,
    ) -> LoanTransitionOutcome:
        """Apply a transition outcome to the provided domain objects."""
        current_status = (
            getattr(loan, "loan_status", None) if loan is not None else None
        )
        outcome = cls.transition(current_status, target_status)

        if loan is not None:
            loan.loan_status = outcome.loan_status

        if asset is not None and outcome.asset_status is not None:
            asset.asset_status = outcome.asset_status

        if locker is not None and outcome.locker_status is not None:
            locker.locker_status = outcome.locker_status

        return outcome

    @staticmethod
    def apply_asset_status(asset: Any, target_status: AssetStatus) -> None:
        """Apply an asset status update for non-loan orchestration flows."""
        asset.asset_status = target_status

    @staticmethod
    def apply_locker_status(locker: Any, target_status: LockerStatus) -> None:
        """Apply a locker status update for non-loan orchestration flows."""
        locker.locker_status = target_status
