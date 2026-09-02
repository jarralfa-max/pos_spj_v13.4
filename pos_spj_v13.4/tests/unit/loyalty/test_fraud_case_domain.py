"""LOY-26 — FraudCase domain entity (master prompt §29)."""

from __future__ import annotations

import pytest

from backend.domain.loyalty.entities.fraud_case import FraudCase
from backend.domain.loyalty.enums import FraudCaseSubjectType
from backend.domain.loyalty.exceptions import (
    InvalidFraudCaseError,
    InvalidFraudCaseStateError,
)
from backend.shared.ids import new_uuid


class TestFraudCase:
    def test_requires_reason(self):
        with pytest.raises(InvalidFraudCaseError):
            FraudCase.open(FraudCaseSubjectType.REFERRAL, new_uuid(), new_uuid(), "",
                           opened_by_user_id=new_uuid())

    def test_open_starts_as_open(self):
        case = FraudCase.open(FraudCaseSubjectType.SWEEPSTAKES_ENTRY, new_uuid(), new_uuid(),
                              "múltiples cuentas del mismo dispositivo",
                              opened_by_user_id=new_uuid())
        assert case.status.value == "OPEN"
        assert case.is_open()

    def test_reviewer_cannot_be_reporter(self):
        reporter = new_uuid()
        case = FraudCase.open(FraudCaseSubjectType.REFERRAL, new_uuid(), new_uuid(), "motivo",
                              opened_by_user_id=reporter)
        with pytest.raises(InvalidFraudCaseStateError):
            case.start_review(reporter)

    def test_confirm_requires_resolution_notes(self):
        case = FraudCase.open(FraudCaseSubjectType.COUPON, new_uuid(), new_uuid(), "motivo",
                              opened_by_user_id=new_uuid())
        case.start_review(new_uuid())
        with pytest.raises(InvalidFraudCaseStateError):
            case.confirm("")

    def test_confirm_happy_path(self):
        case = FraudCase.open(FraudCaseSubjectType.VOUCHER, new_uuid(), new_uuid(), "motivo",
                              opened_by_user_id=new_uuid())
        case.start_review(new_uuid())
        case.confirm("Se confirmó uso duplicado del vale")
        assert case.status.value == "CONFIRMED"
        assert not case.is_open()
        assert case.resolved_at is not None

    def test_dismiss_happy_path(self):
        case = FraudCase.open(FraudCaseSubjectType.TRANSACTION, new_uuid(), new_uuid(), "motivo",
                              opened_by_user_id=new_uuid())
        case.start_review(new_uuid())
        case.dismiss("Falsa alarma, transacción legítima")
        assert case.status.value == "DISMISSED"

    def test_cannot_confirm_before_review(self):
        case = FraudCase.open(FraudCaseSubjectType.MEMBERSHIP, new_uuid(), new_uuid(), "motivo",
                              opened_by_user_id=new_uuid())
        with pytest.raises(InvalidFraudCaseStateError):
            case.confirm("notas")

    def test_cannot_review_twice(self):
        case = FraudCase.open(FraudCaseSubjectType.REFERRAL, new_uuid(), new_uuid(), "motivo",
                              opened_by_user_id=new_uuid())
        case.start_review(new_uuid())
        with pytest.raises(InvalidFraudCaseStateError):
            case.start_review(new_uuid())
