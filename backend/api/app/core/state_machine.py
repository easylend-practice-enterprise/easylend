"""Domain state machine for loan lifecycle transitions.

Centralizes legal loan status transitions and the coupled asset/locker
status outcomes that keep transaction state synchronized.
"""

from dataclasses import dataclass

from app.db.models import AssetStatus, LoanStatus, LockerStatus


class InvalidLoanTransitionError(ValueError):
    """Raised when a requested loan status transition is illegal."""


@dataclass(frozen=True)
class LoanTransitionOutcome:
    """Represents the canonical synchronized status outcome for a transition."""

    loan_status: LoanStatus
    asset_status: AssetStatus | None = None
    locker_status: LockerStatus | None = None


class LoanStateMachine:
    """Validates and resolves legal loan transitions."""

    _INITIAL_STATUSES = {LoanStatus.RESERVED}

    _TRANSITIONS: dict[
        tuple[LoanStatus, LoanStatus],
        LoanTransitionOutcome,
    ] = {
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
        current_status: LoanStatus,
        desired_status: LoanStatus,
    ) -> LoanTransitionOutcome:
        outcome = cls._TRANSITIONS.get((current_status, desired_status))
        if outcome is None:
            raise InvalidLoanTransitionError(
                "Illegal loan transition: "
                f"{current_status.value} -> {desired_status.value}."
            )
        return outcome
