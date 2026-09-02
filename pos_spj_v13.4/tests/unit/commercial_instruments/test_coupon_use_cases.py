"""LOY-12 — Coupon repository round-trip + use cases (Define, Issue,
Validate+Reserve, Confirm, Release, Cancel, Expire)."""

from __future__ import annotations

import sqlite3
from decimal import Decimal

import pytest

from backend.application.commercial_instruments.use_cases.coupon_use_cases import (
    CancelCouponInstanceUseCase,
    ConfirmCouponRedemptionUseCase,
    CreateCouponDefinitionUseCase,
    ExpireCouponsUseCase,
    IssueCouponInstanceUseCase,
    ReleaseCouponReservationUseCase,
    ValidateAndReserveCouponUseCase,
)
from backend.application.loyalty.authorization import LoyaltyAuthorizationPolicy
from backend.domain.commercial_instruments.enums import CommercialBenefitType, CouponType
from backend.infrastructure.db.schema.commercial_instruments_schema import (
    create_commercial_instruments_schema,
)
from backend.shared.ids import new_uuid


@pytest.fixture
def conn():
    c = sqlite3.connect(":memory:")
    c.execute("PRAGMA foreign_keys = ON")
    create_commercial_instruments_schema(c)
    c.commit()
    yield c
    c.close()


@pytest.fixture
def auth():
    return LoyaltyAuthorizationPolicy.permissive_for_tests()


def _definition_id(conn, auth, **overrides) -> str:
    defaults = dict(
        code="WELCOME10", name="10% de bienvenida", coupon_type=CouponType.PUBLIC_CODE,
        benefit_type=CommercialBenefitType.PERCENTAGE, benefit_value=Decimal("10"),
        actor_user_id=new_uuid(), operation_id=new_uuid())
    defaults.update(overrides)
    result = CreateCouponDefinitionUseCase(auth).execute(conn, **defaults)
    return result.entity_id


class TestCreateCouponDefinition:
    def test_creates_definition(self, conn, auth):
        definition_id = _definition_id(conn, auth)
        assert definition_id

    def test_rejects_duplicate_code(self, conn, auth):
        _definition_id(conn, auth)
        result = CreateCouponDefinitionUseCase(auth).execute(
            conn, code="WELCOME10", name="Otro", coupon_type=CouponType.PUBLIC_CODE,
            benefit_type=CommercialBenefitType.FIXED_AMOUNT, benefit_value=Decimal("50"),
            actor_user_id=new_uuid(), operation_id=new_uuid())
        assert not result.success


class TestIssueCouponInstance:
    def test_issues_instance(self, conn, auth):
        definition_id = _definition_id(conn, auth)
        result = IssueCouponInstanceUseCase(auth).execute(
            conn, definition_id=definition_id, code="ABC123", actor_user_id=new_uuid(),
            actor_branch_id=new_uuid(), operation_id=new_uuid())
        assert result.success
        assert result.data["instance"].status == "ACTIVE"

        payload_row = conn.execute(
            "SELECT payload_json FROM commercial_instruments_outbox"
            " WHERE event_name='COUPON_ISSUED'").fetchone()
        import json
        payload = json.loads(payload_row[0])["payload"]
        assert payload["face_value"] == "10"
        assert "instrument_id" in payload

    def test_definition_not_found(self, conn, auth):
        result = IssueCouponInstanceUseCase(auth).execute(
            conn, definition_id=new_uuid(), code="ABC123", actor_user_id=new_uuid(),
            actor_branch_id=new_uuid(), operation_id=new_uuid())
        assert not result.success
        assert result.error_code == "COUPON_DEFINITION_NOT_FOUND"


class TestValidateReserveConfirmFlow:
    def test_full_flow(self, conn, auth):
        definition_id = _definition_id(conn, auth)
        issue = IssueCouponInstanceUseCase(auth).execute(
            conn, definition_id=definition_id, code="ABC123", actor_user_id=new_uuid(),
            actor_branch_id=new_uuid(), operation_id=new_uuid())
        instance_id = issue.entity_id

        sale_id = new_uuid()
        reserve = ValidateAndReserveCouponUseCase(auth).execute(
            conn, code="ABC123", sale_id=sale_id, actor_user_id=new_uuid(),
            actor_branch_id=new_uuid(), operation_id=new_uuid())
        assert reserve.success
        assert reserve.data["instance"].status == "RESERVED"

        confirm = ConfirmCouponRedemptionUseCase(auth).execute(
            conn, coupon_instance_id=instance_id, amount_applied=Decimal("15.00"),
            redeemed_by_user_id=new_uuid(), actor_branch_id=new_uuid(),
            operation_id=new_uuid())
        assert confirm.success
        assert confirm.data["instance"].status == "REDEEMED"

        redemption_row = conn.execute(
            "SELECT amount_applied FROM coupon_redemptions WHERE coupon_instance_id=?",
            (instance_id,)).fetchone()
        assert redemption_row[0] == "15.00"

    def test_reserve_unknown_code(self, conn, auth):
        result = ValidateAndReserveCouponUseCase(auth).execute(
            conn, code="NOPE", sale_id=new_uuid(), actor_user_id=new_uuid(),
            actor_branch_id=new_uuid(), operation_id=new_uuid())
        assert not result.success
        assert result.error_code == "COUPON_NOT_FOUND"

    def test_reserve_rejects_wrong_customer_for_personalized_coupon(self, conn, auth):
        definition_id = _definition_id(conn, auth)
        owner_id = new_uuid()
        IssueCouponInstanceUseCase(auth).execute(
            conn, definition_id=definition_id, code="ABC123", actor_user_id=new_uuid(),
            actor_branch_id=new_uuid(), operation_id=new_uuid(), customer_id=owner_id)
        result = ValidateAndReserveCouponUseCase(auth).execute(
            conn, code="ABC123", sale_id=new_uuid(), actor_user_id=new_uuid(),
            actor_branch_id=new_uuid(), operation_id=new_uuid(), customer_id=new_uuid())
        assert not result.success
        assert result.error_code == "COUPON_NOT_ELIGIBLE"

    def test_reserve_allows_matching_customer(self, conn, auth):
        definition_id = _definition_id(conn, auth)
        owner_id = new_uuid()
        IssueCouponInstanceUseCase(auth).execute(
            conn, definition_id=definition_id, code="ABC123", actor_user_id=new_uuid(),
            actor_branch_id=new_uuid(), operation_id=new_uuid(), customer_id=owner_id)
        result = ValidateAndReserveCouponUseCase(auth).execute(
            conn, code="ABC123", sale_id=new_uuid(), actor_user_id=new_uuid(),
            actor_branch_id=new_uuid(), operation_id=new_uuid(), customer_id=owner_id)
        assert result.success

    def test_release_restores_reservation(self, conn, auth):
        definition_id = _definition_id(conn, auth)
        issue = IssueCouponInstanceUseCase(auth).execute(
            conn, definition_id=definition_id, code="ABC123", actor_user_id=new_uuid(),
            actor_branch_id=new_uuid(), operation_id=new_uuid())
        ValidateAndReserveCouponUseCase(auth).execute(
            conn, code="ABC123", sale_id=new_uuid(), actor_user_id=new_uuid(),
            actor_branch_id=new_uuid(), operation_id=new_uuid())
        result = ReleaseCouponReservationUseCase(auth).execute(
            conn, coupon_instance_id=issue.entity_id, actor_branch_id=new_uuid(),
            operation_id=new_uuid(), actor_user_id=new_uuid())
        assert result.success
        assert result.data["instance"].status == "ACTIVE"

    def test_cannot_reserve_an_already_redeemed_coupon(self, conn, auth):
        definition_id = _definition_id(conn, auth)
        issue = IssueCouponInstanceUseCase(auth).execute(
            conn, definition_id=definition_id, code="ABC123", actor_user_id=new_uuid(),
            actor_branch_id=new_uuid(), operation_id=new_uuid())
        ValidateAndReserveCouponUseCase(auth).execute(
            conn, code="ABC123", sale_id=new_uuid(), actor_user_id=new_uuid(),
            actor_branch_id=new_uuid(), operation_id=new_uuid())
        ConfirmCouponRedemptionUseCase(auth).execute(
            conn, coupon_instance_id=issue.entity_id, amount_applied=Decimal("15.00"),
            redeemed_by_user_id=new_uuid(), actor_branch_id=new_uuid(),
            operation_id=new_uuid())
        result = ValidateAndReserveCouponUseCase(auth).execute(
            conn, code="ABC123", sale_id=new_uuid(), actor_user_id=new_uuid(),
            actor_branch_id=new_uuid(), operation_id=new_uuid())
        assert not result.success
        assert result.error_code == "COUPON_ALREADY_REDEEMED"


class TestCancelAndExpire:
    def test_cancel_requires_reason(self, conn, auth):
        definition_id = _definition_id(conn, auth)
        issue = IssueCouponInstanceUseCase(auth).execute(
            conn, definition_id=definition_id, code="ABC123", actor_user_id=new_uuid(),
            actor_branch_id=new_uuid(), operation_id=new_uuid())
        result = CancelCouponInstanceUseCase(auth).execute(
            conn, coupon_instance_id=issue.entity_id, reason="", actor_user_id=new_uuid(),
            actor_branch_id=new_uuid(), operation_id=new_uuid())
        assert not result.success

    def test_expire_marks_instances_past_validity(self, conn, auth):
        definition_id = _definition_id(
            conn, auth, code="OLD10", valid_to="2020-01-01T00:00:00+00:00")
        issue = IssueCouponInstanceUseCase(auth).execute(
            conn, definition_id=definition_id, code="OLD-INST", actor_user_id=new_uuid(),
            actor_branch_id=new_uuid(), operation_id=new_uuid())

        result = ExpireCouponsUseCase(auth).execute(
            conn, now_iso="2026-01-01T00:00:00+00:00", operation_id_prefix=new_uuid())
        assert result.success
        assert issue.entity_id in result.data["expired_instance_ids"]
