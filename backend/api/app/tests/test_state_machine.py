from types import SimpleNamespace

import pytest

from app.core.state_machine import InvalidLoanTransitionError, LoanStateMachine
from app.db.models import AssetStatus, LoanStatus, LockerStatus


def test_apply_transition_supports_initial_reservation_from_none() -> None:
    loan = SimpleNamespace(loan_status=None)
    asset = SimpleNamespace(asset_status=AssetStatus.AVAILABLE)
    locker = SimpleNamespace(locker_status=LockerStatus.OCCUPIED)

    outcome = LoanStateMachine.apply_transition(
        loan,
        asset,
        locker,
        LoanStatus.RESERVED,
    )

    assert outcome.loan_status == LoanStatus.RESERVED
    assert outcome.asset_status == AssetStatus.BORROWED
    assert outcome.locker_status is None
    assert outcome.suspend_users is False

    assert loan.loan_status == LoanStatus.RESERVED
    assert asset.asset_status == AssetStatus.BORROWED
    assert locker.locker_status == LockerStatus.OCCUPIED


def test_apply_transition_dispute_from_active_suspends_users() -> None:
    loan = SimpleNamespace(loan_status=LoanStatus.ACTIVE)
    asset = SimpleNamespace(asset_status=AssetStatus.BORROWED)
    locker = SimpleNamespace(locker_status=LockerStatus.AVAILABLE)

    outcome = LoanStateMachine.apply_transition(
        loan,
        asset,
        locker,
        LoanStatus.DISPUTED,
    )

    assert outcome.loan_status == LoanStatus.DISPUTED
    assert outcome.asset_status == AssetStatus.MAINTENANCE
    assert outcome.locker_status == LockerStatus.MAINTENANCE
    assert outcome.suspend_users is True

    assert loan.loan_status == LoanStatus.DISPUTED
    assert asset.asset_status == AssetStatus.MAINTENANCE
    assert locker.locker_status == LockerStatus.MAINTENANCE


def test_apply_transition_dispute_from_fraud_suspected_suspends_users() -> None:
    loan = SimpleNamespace(loan_status=LoanStatus.FRAUD_SUSPECTED)
    asset = SimpleNamespace(asset_status=AssetStatus.PENDING_INSPECTION)
    locker = SimpleNamespace(locker_status=LockerStatus.MAINTENANCE)

    outcome = LoanStateMachine.apply_transition(
        loan,
        asset,
        locker,
        LoanStatus.DISPUTED,
    )

    assert outcome.suspend_users is True
    assert loan.loan_status == LoanStatus.DISPUTED
    assert asset.asset_status == AssetStatus.MAINTENANCE
    assert locker.locker_status == LockerStatus.MAINTENANCE


def test_apply_transition_raises_on_illegal_path() -> None:
    loan = SimpleNamespace(loan_status=LoanStatus.COMPLETED)
    asset = SimpleNamespace(asset_status=AssetStatus.AVAILABLE)
    locker = SimpleNamespace(locker_status=LockerStatus.AVAILABLE)

    with pytest.raises(InvalidLoanTransitionError):
        LoanStateMachine.apply_transition(
            loan,
            asset,
            locker,
            LoanStatus.RESERVED,
        )
