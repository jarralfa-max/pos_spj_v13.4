"""LOY-6 — Points ledger use cases: Accrue, Reserve, Confirm, Release,
Redeem, Adjust, Reverse, Expire."""

from __future__ import annotations

import json
import sqlite3
from decimal import Decimal

import pytest

from backend.application.loyalty.authorization import LoyaltyAuthorizationPolicy
from backend.application.loyalty.use_cases.ledger_use_cases import (
    AccrueLoyaltyPointsUseCase,
    AdjustLoyaltyPointsUseCase,
    ConfirmReservedLoyaltyPointsUseCase,
    ExpireLoyaltyPointsUseCase,
    RedeemLoyaltyPointsUseCase,
    ReleaseLoyaltyPointsUseCase,
    ReserveLoyaltyPointsUseCase,
    ReverseLoyaltyTransactionUseCase,
)
from backend.domain.loyalty.entities.loyalty_account import LoyaltyAccount
from backend.domain.loyalty.entities.loyalty_transaction import LoyaltyTransaction
from backend.domain.loyalty.policies.balance_policy import LoyaltyBalancePolicy
from backend.infrastructure.db.repositories.loyalty.account_repository import (
    LoyaltyAccountRepository,
)
from backend.infrastructure.db.repositories.loyalty.transaction_repository import (
    LoyaltyTransactionRepository,
)
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


@pytest.fixture
def account(conn):
    account = LoyaltyAccount.create(new_uuid())
    LoyaltyAccountRepository(conn).save(account)
    return account


def _balance(conn, account_id) -> Decimal:
    ledger = LoyaltyTransactionRepository(conn).list_for_account(account_id)
    return LoyaltyBalancePolicy.balance(ledger)


class TestAccrue:
    def test_accrues_points(self, conn, auth, account):
        result = AccrueLoyaltyPointsUseCase(auth).execute(
            conn, loyalty_account_id=account.id, points_amount=Decimal("100"),
            operation_id=new_uuid(), actor_user_id=new_uuid(), actor_branch_id=new_uuid(),
            source_module="sales", source_document_id=new_uuid(), reason_code="SALE_ACCRUAL")
        assert result.success
        assert _balance(conn, account.id) == Decimal("100")

    def test_blocks_double_accrual_for_same_source(self, conn, auth, account):
        sale_id = new_uuid()
        AccrueLoyaltyPointsUseCase(auth).execute(
            conn, loyalty_account_id=account.id, points_amount=Decimal("100"),
            operation_id=new_uuid(), actor_user_id=new_uuid(), actor_branch_id=new_uuid(),
            source_module="sales", source_document_id=sale_id, reason_code="SALE_ACCRUAL")
        result = AccrueLoyaltyPointsUseCase(auth).execute(
            conn, loyalty_account_id=account.id, points_amount=Decimal("100"),
            operation_id=new_uuid(), actor_user_id=new_uuid(), actor_branch_id=new_uuid(),
            source_module="sales", source_document_id=sale_id, reason_code="SALE_ACCRUAL")
        assert not result.success
        assert _balance(conn, account.id) == Decimal("100")

    def test_account_not_found(self, conn, auth):
        result = AccrueLoyaltyPointsUseCase(auth).execute(
            conn, loyalty_account_id=new_uuid(), points_amount=Decimal("10"),
            operation_id=new_uuid(), actor_user_id=new_uuid(), actor_branch_id=new_uuid(),
            source_module="sales")
        assert not result.success
        assert result.error_code == "ACCOUNT_NOT_FOUND"

    def test_finance_aligned_payload_shape(self, conn, auth, account):
        AccrueLoyaltyPointsUseCase(auth).execute(
            conn, loyalty_account_id=account.id, points_amount=Decimal("100"),
            operation_id=new_uuid(), actor_user_id=new_uuid(), actor_branch_id=new_uuid(),
            source_module="sales", estimated_fair_value=Decimal("10.00"),
            currency_code="MXN")
        row = conn.execute(
            "SELECT payload_json FROM loyalty_outbox WHERE event_name='LOYALTY_POINTS_ISSUED'"
        ).fetchone()
        payload = json.loads(row[0])["payload"]
        assert payload["estimated_fair_value"] == "10.00"
        assert payload["currency_code"] == "MXN"
        assert "loyalty_transaction_id" in payload
        assert payload["customer_id"] == account.customer_id


class TestReserveConfirmRelease:
    def test_reserve_reduces_balance_immediately(self, conn, auth, account):
        AccrueLoyaltyPointsUseCase(auth).execute(
            conn, loyalty_account_id=account.id, points_amount=Decimal("100"),
            operation_id=new_uuid(), actor_user_id=new_uuid(), actor_branch_id=new_uuid(),
            source_module="sales")
        result = ReserveLoyaltyPointsUseCase(auth).execute(
            conn, loyalty_account_id=account.id, points_amount=Decimal("30"),
            operation_id=new_uuid(), actor_user_id=new_uuid(), actor_branch_id=new_uuid())
        assert result.success
        assert _balance(conn, account.id) == Decimal("70")

    def test_reserve_rejects_insufficient_balance(self, conn, auth, account):
        result = ReserveLoyaltyPointsUseCase(auth).execute(
            conn, loyalty_account_id=account.id, points_amount=Decimal("30"),
            operation_id=new_uuid(), actor_user_id=new_uuid(), actor_branch_id=new_uuid())
        assert not result.success
        assert result.error_code == "INSUFFICIENT_POINTS"

    def test_confirm_does_not_change_balance_further(self, conn, auth, account):
        AccrueLoyaltyPointsUseCase(auth).execute(
            conn, loyalty_account_id=account.id, points_amount=Decimal("100"),
            operation_id=new_uuid(), actor_user_id=new_uuid(), actor_branch_id=new_uuid(),
            source_module="sales")
        reserve = ReserveLoyaltyPointsUseCase(auth).execute(
            conn, loyalty_account_id=account.id, points_amount=Decimal("30"),
            operation_id=new_uuid(), actor_user_id=new_uuid(), actor_branch_id=new_uuid())
        balance_after_reserve = _balance(conn, account.id)
        confirm = ConfirmReservedLoyaltyPointsUseCase(auth).execute(
            conn, transaction_id=reserve.entity_id, actor_user_id=new_uuid(),
            actor_branch_id=new_uuid(), operation_id=new_uuid())
        assert confirm.success
        assert _balance(conn, account.id) == balance_after_reserve

    def test_release_restores_balance(self, conn, auth, account):
        AccrueLoyaltyPointsUseCase(auth).execute(
            conn, loyalty_account_id=account.id, points_amount=Decimal("100"),
            operation_id=new_uuid(), actor_user_id=new_uuid(), actor_branch_id=new_uuid(),
            source_module="sales")
        reserve = ReserveLoyaltyPointsUseCase(auth).execute(
            conn, loyalty_account_id=account.id, points_amount=Decimal("30"),
            operation_id=new_uuid(), actor_user_id=new_uuid(), actor_branch_id=new_uuid())
        release = ReleaseLoyaltyPointsUseCase(auth).execute(
            conn, transaction_id=reserve.entity_id, actor_user_id=new_uuid(),
            actor_branch_id=new_uuid(), operation_id=new_uuid())
        assert release.success
        assert _balance(conn, account.id) == Decimal("100")

    def test_cannot_release_an_already_consumed_reservation(self, conn, auth, account):
        AccrueLoyaltyPointsUseCase(auth).execute(
            conn, loyalty_account_id=account.id, points_amount=Decimal("100"),
            operation_id=new_uuid(), actor_user_id=new_uuid(), actor_branch_id=new_uuid(),
            source_module="sales")
        reserve = ReserveLoyaltyPointsUseCase(auth).execute(
            conn, loyalty_account_id=account.id, points_amount=Decimal("30"),
            operation_id=new_uuid(), actor_user_id=new_uuid(), actor_branch_id=new_uuid())
        ConfirmReservedLoyaltyPointsUseCase(auth).execute(
            conn, transaction_id=reserve.entity_id, actor_user_id=new_uuid(),
            actor_branch_id=new_uuid(), operation_id=new_uuid())
        result = ReleaseLoyaltyPointsUseCase(auth).execute(
            conn, transaction_id=reserve.entity_id, actor_user_id=new_uuid(),
            actor_branch_id=new_uuid(), operation_id=new_uuid())
        assert not result.success
        assert result.error_code == "TRANSACTION_INVALID_STATE"


class TestRedeem:
    def test_redeem_reduces_balance(self, conn, auth, account):
        AccrueLoyaltyPointsUseCase(auth).execute(
            conn, loyalty_account_id=account.id, points_amount=Decimal("100"),
            operation_id=new_uuid(), actor_user_id=new_uuid(), actor_branch_id=new_uuid(),
            source_module="sales")
        result = RedeemLoyaltyPointsUseCase(auth).execute(
            conn, loyalty_account_id=account.id, points_amount=Decimal("40"),
            operation_id=new_uuid(), actor_user_id=new_uuid(), actor_branch_id=new_uuid())
        assert result.success
        assert _balance(conn, account.id) == Decimal("60")

    def test_redeem_rejects_insufficient_balance(self, conn, auth, account):
        result = RedeemLoyaltyPointsUseCase(auth).execute(
            conn, loyalty_account_id=account.id, points_amount=Decimal("40"),
            operation_id=new_uuid(), actor_user_id=new_uuid(), actor_branch_id=new_uuid())
        assert not result.success
        assert result.error_code == "INSUFFICIENT_POINTS"


class TestAdjust:
    def test_adjust_requires_distinct_authorizer(self, conn, auth, account):
        actor = new_uuid()
        result = AdjustLoyaltyPointsUseCase(auth).execute(
            conn, loyalty_account_id=account.id, points_amount=Decimal("15"),
            reason_code="CORRECCION", requested_by=actor, authorizer_user_id=actor,
            actor_branch_id=new_uuid(), operation_id=new_uuid())
        assert not result.success
        assert result.error_code == "SEGREGATION_OF_DUTIES"

    def test_adjust_with_distinct_authorizer_succeeds(self, conn, auth, account):
        result = AdjustLoyaltyPointsUseCase(auth).execute(
            conn, loyalty_account_id=account.id, points_amount=Decimal("15"),
            reason_code="CORRECCION", requested_by=new_uuid(),
            authorizer_user_id=new_uuid(), actor_branch_id=new_uuid(),
            operation_id=new_uuid())
        assert result.success
        assert _balance(conn, account.id) == Decimal("15")


class TestReverse:
    def test_reverse_nets_balance_to_zero(self, conn, auth, account):
        accrue = AccrueLoyaltyPointsUseCase(auth).execute(
            conn, loyalty_account_id=account.id, points_amount=Decimal("100"),
            operation_id=new_uuid(), actor_user_id=new_uuid(), actor_branch_id=new_uuid(),
            source_module="sales")
        result = ReverseLoyaltyTransactionUseCase(auth).execute(
            conn, transaction_id=accrue.entity_id, reason_code="ERROR_CAPTURA",
            actor_user_id=new_uuid(), actor_branch_id=new_uuid(), operation_id=new_uuid())
        assert result.success
        assert _balance(conn, account.id) == Decimal("0")

    def test_cannot_reverse_twice(self, conn, auth, account):
        accrue = AccrueLoyaltyPointsUseCase(auth).execute(
            conn, loyalty_account_id=account.id, points_amount=Decimal("100"),
            operation_id=new_uuid(), actor_user_id=new_uuid(), actor_branch_id=new_uuid(),
            source_module="sales")
        ReverseLoyaltyTransactionUseCase(auth).execute(
            conn, transaction_id=accrue.entity_id, reason_code="ERROR_CAPTURA",
            actor_user_id=new_uuid(), actor_branch_id=new_uuid(), operation_id=new_uuid())
        result = ReverseLoyaltyTransactionUseCase(auth).execute(
            conn, transaction_id=accrue.entity_id, reason_code="ERROR_CAPTURA",
            actor_user_id=new_uuid(), actor_branch_id=new_uuid(), operation_id=new_uuid())
        assert not result.success
        assert result.error_code == "TRANSACTION_INVALID_STATE"


class TestExpire:
    def test_expires_available_points_past_their_expiry(self, conn, auth, account):
        repo = LoyaltyTransactionRepository(conn)
        past = LoyaltyTransaction.earn(
            loyalty_account_id=account.id, points_amount=Decimal("50"),
            operation_id=new_uuid(), expires_at="2020-01-01T00:00:00+00:00",
            branch_id=new_uuid())
        repo.save(past)
        future = LoyaltyTransaction.earn(
            loyalty_account_id=account.id, points_amount=Decimal("20"),
            operation_id=new_uuid(), expires_at="2099-01-01T00:00:00+00:00",
            branch_id=new_uuid())
        repo.save(future)

        result = ExpireLoyaltyPointsUseCase(auth).execute(
            conn, before_iso="2026-01-01T00:00:00+00:00", operation_id_prefix=new_uuid())
        assert result.success
        assert result.data["expired_transaction_ids"] == [past.id]
        assert _balance(conn, account.id) == Decimal("20")
