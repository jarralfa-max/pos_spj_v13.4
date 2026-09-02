"""LOY-13 — Voucher use cases: Define, Issue, Reserve, Confirm (partial and
full), Release."""

from __future__ import annotations

import sqlite3
from decimal import Decimal

import pytest

from backend.application.commercial_instruments.use_cases.voucher_use_cases import (
    ConfirmVoucherRedemptionUseCase,
    CreateVoucherDefinitionUseCase,
    IssueVoucherInstanceUseCase,
    ReleaseVoucherReservationUseCase,
    ReserveVoucherAmountUseCase,
)
from backend.application.loyalty.authorization import LoyaltyAuthorizationPolicy
from backend.domain.commercial_instruments.enums import VoucherType
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


def _issued_voucher(conn, auth, amount="500"):
    define = CreateVoucherDefinitionUseCase(auth).execute(
        conn, code="REFUND", name="Vale de devolución", voucher_type=VoucherType.REFUND_VOUCHER,
        actor_user_id=new_uuid(), operation_id=new_uuid())
    issue = IssueVoucherInstanceUseCase(auth).execute(
        conn, definition_id=define.entity_id, code="VAL-001", amount=Decimal(amount),
        actor_user_id=new_uuid(), actor_branch_id=new_uuid(), operation_id=new_uuid())
    return issue.entity_id


class TestCreateAndIssue:
    def test_issue_creates_ledger_entry(self, conn, auth):
        instance_id = _issued_voucher(conn, auth, "500")
        assert instance_id
        row = conn.execute(
            "SELECT amount FROM voucher_transactions WHERE voucher_instance_id=?",
            (instance_id,)).fetchone()
        assert row[0] == "500"

    def test_definition_not_found(self, conn, auth):
        result = IssueVoucherInstanceUseCase(auth).execute(
            conn, definition_id=new_uuid(), code="VAL-001", amount=Decimal("100"),
            actor_user_id=new_uuid(), actor_branch_id=new_uuid(), operation_id=new_uuid())
        assert not result.success
        assert result.error_code == "VOUCHER_DEFINITION_NOT_FOUND"


class TestReserveConfirmFlow:
    def test_partial_redemption_leaves_voucher_partially_redeemed(self, conn, auth):
        instance_id = _issued_voucher(conn, auth, "500")
        reserve = ReserveVoucherAmountUseCase(auth).execute(
            conn, voucher_instance_id=instance_id, amount=Decimal("200"), sale_id=new_uuid(),
            actor_branch_id=new_uuid(), operation_id=new_uuid())
        assert reserve.success

        confirm = ConfirmVoucherRedemptionUseCase(auth).execute(
            conn, reservation_transaction_id=reserve.entity_id, redeemed_by_user_id=new_uuid(),
            actor_branch_id=new_uuid(), operation_id=new_uuid())
        assert confirm.success
        assert confirm.data["instance"].status == "PARTIALLY_REDEEMED"
        assert confirm.data["instance"].balance == Decimal("300")

    def test_full_redemption_marks_voucher_redeemed(self, conn, auth):
        instance_id = _issued_voucher(conn, auth, "200")
        reserve = ReserveVoucherAmountUseCase(auth).execute(
            conn, voucher_instance_id=instance_id, amount=Decimal("200"), sale_id=new_uuid(),
            actor_branch_id=new_uuid(), operation_id=new_uuid())
        confirm = ConfirmVoucherRedemptionUseCase(auth).execute(
            conn, reservation_transaction_id=reserve.entity_id, redeemed_by_user_id=new_uuid(),
            actor_branch_id=new_uuid(), operation_id=new_uuid())
        assert confirm.data["instance"].status == "REDEEMED"
        assert confirm.data["instance"].balance == Decimal("0")

    def test_reserve_rejects_insufficient_balance(self, conn, auth):
        instance_id = _issued_voucher(conn, auth, "100")
        result = ReserveVoucherAmountUseCase(auth).execute(
            conn, voucher_instance_id=instance_id, amount=Decimal("200"), sale_id=new_uuid(),
            actor_branch_id=new_uuid(), operation_id=new_uuid())
        assert not result.success
        assert result.error_code == "VOUCHER_INSUFFICIENT_BALANCE"

    def test_second_partial_redemption_after_first(self, conn, auth):
        instance_id = _issued_voucher(conn, auth, "500")
        r1 = ReserveVoucherAmountUseCase(auth).execute(
            conn, voucher_instance_id=instance_id, amount=Decimal("200"), sale_id=new_uuid(),
            actor_branch_id=new_uuid(), operation_id=new_uuid())
        ConfirmVoucherRedemptionUseCase(auth).execute(
            conn, reservation_transaction_id=r1.entity_id, redeemed_by_user_id=new_uuid(),
            actor_branch_id=new_uuid(), operation_id=new_uuid())

        r2 = ReserveVoucherAmountUseCase(auth).execute(
            conn, voucher_instance_id=instance_id, amount=Decimal("300"), sale_id=new_uuid(),
            actor_branch_id=new_uuid(), operation_id=new_uuid())
        confirm2 = ConfirmVoucherRedemptionUseCase(auth).execute(
            conn, reservation_transaction_id=r2.entity_id, redeemed_by_user_id=new_uuid(),
            actor_branch_id=new_uuid(), operation_id=new_uuid())
        assert confirm2.data["instance"].status == "REDEEMED"
        assert confirm2.data["instance"].balance == Decimal("0")

        redemptions = conn.execute(
            "SELECT COUNT(*) FROM voucher_redemptions WHERE voucher_instance_id=?",
            (instance_id,)).fetchone()
        assert redemptions[0] == 2

    def test_release_restores_balance_and_active_status(self, conn, auth):
        instance_id = _issued_voucher(conn, auth, "500")
        reserve = ReserveVoucherAmountUseCase(auth).execute(
            conn, voucher_instance_id=instance_id, amount=Decimal("200"), sale_id=new_uuid(),
            actor_branch_id=new_uuid(), operation_id=new_uuid())
        release = ReleaseVoucherReservationUseCase(auth).execute(
            conn, reservation_transaction_id=reserve.entity_id, actor_branch_id=new_uuid(),
            operation_id=new_uuid(), actor_user_id=new_uuid())
        assert release.success
        assert release.data["instance"].status == "ACTIVE"
        assert release.data["instance"].balance == Decimal("500")

    def test_release_after_prior_redemption_restores_partially_redeemed(self, conn, auth):
        instance_id = _issued_voucher(conn, auth, "500")
        r1 = ReserveVoucherAmountUseCase(auth).execute(
            conn, voucher_instance_id=instance_id, amount=Decimal("100"), sale_id=new_uuid(),
            actor_branch_id=new_uuid(), operation_id=new_uuid())
        ConfirmVoucherRedemptionUseCase(auth).execute(
            conn, reservation_transaction_id=r1.entity_id, redeemed_by_user_id=new_uuid(),
            actor_branch_id=new_uuid(), operation_id=new_uuid())

        r2 = ReserveVoucherAmountUseCase(auth).execute(
            conn, voucher_instance_id=instance_id, amount=Decimal("200"), sale_id=new_uuid(),
            actor_branch_id=new_uuid(), operation_id=new_uuid())
        release = ReleaseVoucherReservationUseCase(auth).execute(
            conn, reservation_transaction_id=r2.entity_id, actor_branch_id=new_uuid(),
            operation_id=new_uuid(), actor_user_id=new_uuid())
        assert release.data["instance"].status == "PARTIALLY_REDEEMED"
        assert release.data["instance"].balance == Decimal("400")

    def test_voucher_not_found(self, conn, auth):
        result = ReserveVoucherAmountUseCase(auth).execute(
            conn, voucher_instance_id=new_uuid(), amount=Decimal("100"), sale_id=new_uuid(),
            actor_branch_id=new_uuid(), operation_id=new_uuid())
        assert not result.success
        assert result.error_code == "VOUCHER_NOT_FOUND"
