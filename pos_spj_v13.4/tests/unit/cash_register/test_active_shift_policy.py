"""SDLC-ARQ-SHIFT-001: una sola definición de estados activos y de qué se
puede hacer con cada uno (decisión 2026-11-02)."""
import pytest

from backend.domain.cash_register.enums import CashShiftOperability, CashShiftStatus
from backend.domain.cash_register.exceptions import (
    CashInvalidStateError, CashShiftClosingError, CashShiftNotOpenError,
    CashShiftSuspendedError,
)
from backend.domain.cash_register.policies.workflow_policies import CashShiftLifecyclePolicy as P


def test_active_values_are_the_active_set_as_sorted_text():
    assert P.active_status_values() == tuple(sorted(s.value for s in P.ACTIVE_STATUSES))
    assert set(P.active_status_values()).isdisjoint(s.value for s in P.FINAL_STATUSES)


def test_closing_statuses_are_active_and_exclude_open_and_suspended():
    assert P.CLOSING_STATUSES < P.ACTIVE_STATUSES
    assert CashShiftStatus.OPEN not in P.CLOSING_STATUSES
    assert CashShiftStatus.SUSPENDED not in P.CLOSING_STATUSES
    assert P.closing_status_values() == (
        "CLOSING", "COUNTED", "COUNTING", "PENDING_COUNT", "PENDING_REVIEW")


@pytest.mark.parametrize("status, expected", [
    ("OPEN", CashShiftOperability.OPERABLE),
    ("SUSPENDED", CashShiftOperability.MUST_RESUME),
    ("CLOSING", CashShiftOperability.MUST_OPEN_NEW),
    ("PENDING_COUNT", CashShiftOperability.MUST_OPEN_NEW),
    ("OPENING", CashShiftOperability.MUST_OPEN_NEW),
    (CashShiftStatus.OPEN, CashShiftOperability.OPERABLE),
])
def test_operability_follows_the_approved_decision(status, expected):
    assert P.operability(status) is expected


def test_operability_rejects_unknown_status():
    with pytest.raises(CashInvalidStateError):
        P.operability("WHATEVER")


def test_not_open_errors_keep_the_shift_identity_and_old_catch_clauses_work():
    error = CashShiftSuspendedError("x", shift_id="s-1", status="SUSPENDED")
    assert isinstance(error, CashShiftNotOpenError)
    assert isinstance(error, CashInvalidStateError)
    assert (error.shift_id, error.status) == ("s-1", "SUSPENDED")
    assert issubclass(CashShiftClosingError, CashShiftNotOpenError)
    assert CashShiftNotOpenError("sin turno").shift_id is None
