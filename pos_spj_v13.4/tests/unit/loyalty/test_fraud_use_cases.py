"""LOY-26 — Fraud case use cases (master prompt §29)."""

from __future__ import annotations

import sqlite3

import pytest

from backend.application.loyalty.authorization import LoyaltyAuthorizationPolicy
from backend.application.loyalty.use_cases.fraud_use_cases import (
    ConfirmFraudCaseUseCase,
    DismissFraudCaseUseCase,
    OpenFraudCaseUseCase,
    StartFraudCaseReviewUseCase,
)
from backend.domain.loyalty.enums import FraudCaseSubjectType
from backend.infrastructure.db.repositories.loyalty.unit_of_work import LoyaltyUnitOfWork
from backend.infrastructure.db.schema.loyalty_schema import create_loyalty_schema
from backend.shared.ids import new_uuid


@pytest.fixture
def conn():
    c = sqlite3.connect(":memory:")
    c.execute("PRAGMA foreign_keys = ON")
    create_loyalty_schema(c)
    c.commit()
    yield c
    c.close()


@pytest.fixture
def auth():
    return LoyaltyAuthorizationPolicy.permissive_for_tests()


class TestOpenFraudCase:
    def test_open_case(self, conn, auth):
        result = OpenFraudCaseUseCase(auth).execute(
            conn, subject_type=FraudCaseSubjectType.SWEEPSTAKES_ENTRY, subject_id=new_uuid(),
            customer_id=new_uuid(), reason="múltiples cuentas del mismo dispositivo",
            actor_user_id=new_uuid(), actor_branch_id=new_uuid(), operation_id=new_uuid())
        assert result.success
        with LoyaltyUnitOfWork(conn) as uow:
            case = uow.fraud_cases.get(result.entity_id)
            assert case.status.value == "OPEN"


class TestFraudCaseWorkflow:
    def _open_case(self, conn, auth):
        result = OpenFraudCaseUseCase(auth).execute(
            conn, subject_type=FraudCaseSubjectType.COUPON, subject_id=new_uuid(),
            customer_id=new_uuid(), reason="motivo", actor_user_id=new_uuid(),
            actor_branch_id=new_uuid(), operation_id=new_uuid())
        return result.entity_id

    def test_full_workflow_confirm(self, conn, auth):
        case_id = self._open_case(conn, auth)
        review = StartFraudCaseReviewUseCase(auth).execute(
            conn, case_id=case_id, actor_user_id=new_uuid(), actor_branch_id=new_uuid(),
            operation_id=new_uuid())
        assert review.success
        confirm = ConfirmFraudCaseUseCase(auth).execute(
            conn, case_id=case_id, resolution_notes="Confirmado tras revisión",
            actor_user_id=new_uuid(), actor_branch_id=new_uuid(), operation_id=new_uuid())
        assert confirm.success
        with LoyaltyUnitOfWork(conn) as uow:
            assert uow.fraud_cases.get(case_id).status.value == "CONFIRMED"

    def test_full_workflow_dismiss(self, conn, auth):
        case_id = self._open_case(conn, auth)
        StartFraudCaseReviewUseCase(auth).execute(
            conn, case_id=case_id, actor_user_id=new_uuid(), actor_branch_id=new_uuid(),
            operation_id=new_uuid())
        dismiss = DismissFraudCaseUseCase(auth).execute(
            conn, case_id=case_id, resolution_notes="Falsa alarma", actor_user_id=new_uuid(),
            actor_branch_id=new_uuid(), operation_id=new_uuid())
        assert dismiss.success
        with LoyaltyUnitOfWork(conn) as uow:
            assert uow.fraud_cases.get(case_id).status.value == "DISMISSED"

    def test_case_not_found(self, conn, auth):
        result = StartFraudCaseReviewUseCase(auth).execute(
            conn, case_id=new_uuid(), actor_user_id=new_uuid(), actor_branch_id=new_uuid(),
            operation_id=new_uuid())
        assert not result.success
        assert result.error_code == "FRAUD_CASE_NOT_FOUND"
