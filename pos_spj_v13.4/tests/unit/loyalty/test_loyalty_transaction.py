"""LOY-2 — LoyaltyTransaction ledger entry (master prompt §11)."""

from __future__ import annotations

from decimal import Decimal

import pytest

from backend.domain.loyalty.entities.loyalty_transaction import LoyaltyTransaction
from backend.domain.loyalty.enums import TransactionStatus, TransactionType
from backend.domain.loyalty.exceptions import (
    InvalidLoyaltyTransactionAmountError,
    InvalidLoyaltyTransactionStateError,
)
from backend.shared.ids import new_uuid


def _account_id() -> str:
    return new_uuid()


def _op() -> str:
    return new_uuid()


class TestLoyaltyTransactionFactories:
    def test_earn_is_available_and_positive(self):
        txn = LoyaltyTransaction.earn(
            loyalty_account_id=_account_id(), points_amount=Decimal("100"),
            operation_id=_op())
        assert txn.transaction_type is TransactionType.EARN
        assert txn.status is TransactionStatus.AVAILABLE
        assert txn.points_amount == Decimal("100")

    def test_earn_rejects_negative_amount(self):
        with pytest.raises(InvalidLoyaltyTransactionAmountError):
            LoyaltyTransaction.earn(loyalty_account_id=_account_id(),
                                     points_amount=Decimal("-1"), operation_id=_op())

    def test_earn_rejects_float(self):
        with pytest.raises(InvalidLoyaltyTransactionAmountError):
            LoyaltyTransaction.earn(loyalty_account_id=_account_id(),
                                     points_amount=100.0, operation_id=_op())

    def test_earn_rejects_zero(self):
        with pytest.raises(InvalidLoyaltyTransactionAmountError):
            LoyaltyTransaction.earn(loyalty_account_id=_account_id(),
                                     points_amount=Decimal("0"), operation_id=_op())

    def test_redeem_requires_negative_amount(self):
        with pytest.raises(InvalidLoyaltyTransactionAmountError):
            LoyaltyTransaction.redeem(loyalty_account_id=_account_id(),
                                       points_amount=Decimal("50"), operation_id=_op())
        txn = LoyaltyTransaction.redeem(loyalty_account_id=_account_id(),
                                         points_amount=Decimal("-50"), operation_id=_op())
        assert txn.points_amount == Decimal("-50")

    def test_reserve_starts_reserved(self):
        txn = LoyaltyTransaction.reserve(
            loyalty_account_id=_account_id(), points_amount=Decimal("-20"),
            operation_id=_op())
        assert txn.status is TransactionStatus.RESERVED

    def test_pending_when_available_at_is_set(self):
        txn = LoyaltyTransaction.earn(
            loyalty_account_id=_account_id(), points_amount=Decimal("10"),
            operation_id=_op(), available_at="2099-01-01T00:00:00+00:00")
        assert txn.status is TransactionStatus.PENDING

    def test_adjustment_requires_reason_code(self):
        with pytest.raises(InvalidLoyaltyTransactionAmountError):
            LoyaltyTransaction.adjustment(
                loyalty_account_id=_account_id(), points_amount=Decimal("5"),
                operation_id=_op(), reason_code="")

    def test_adjustment_allows_either_sign(self):
        pos = LoyaltyTransaction.adjustment(
            loyalty_account_id=_account_id(), points_amount=Decimal("5"),
            operation_id=_op(), reason_code="CORRECCION")
        neg = LoyaltyTransaction.adjustment(
            loyalty_account_id=_account_id(), points_amount=Decimal("-5"),
            operation_id=_op(), reason_code="CORRECCION")
        assert pos.points_amount == Decimal("5")
        assert neg.points_amount == Decimal("-5")


class TestLoyaltyTransactionReservationFlow:
    def test_release_of_offsets_reservation(self):
        reservation = LoyaltyTransaction.reserve(
            loyalty_account_id=_account_id(), points_amount=Decimal("-30"),
            operation_id=_op())
        release = LoyaltyTransaction.release_of(reservation, operation_id=_op())
        assert release.transaction_type is TransactionType.RELEASE
        assert release.points_amount == Decimal("30")
        reservation.cancel_reservation()
        assert reservation.status is TransactionStatus.CANCELLED

    def test_release_of_rejects_non_reservation(self):
        earn = LoyaltyTransaction.earn(loyalty_account_id=_account_id(),
                                        points_amount=Decimal("10"), operation_id=_op())
        with pytest.raises(InvalidLoyaltyTransactionStateError):
            LoyaltyTransaction.release_of(earn, operation_id=_op())

    def test_mark_consumed_requires_reserved_status(self):
        earn = LoyaltyTransaction.earn(loyalty_account_id=_account_id(),
                                        points_amount=Decimal("10"), operation_id=_op())
        with pytest.raises(InvalidLoyaltyTransactionStateError):
            earn.mark_consumed()

    def test_cannot_cancel_a_consumed_reservation(self):
        reservation = LoyaltyTransaction.reserve(
            loyalty_account_id=_account_id(), points_amount=Decimal("-30"),
            operation_id=_op())
        reservation.mark_consumed()
        with pytest.raises(InvalidLoyaltyTransactionStateError):
            reservation.cancel_reservation()


class TestLoyaltyTransactionReversal:
    def test_reversal_of_flips_sign(self):
        earn = LoyaltyTransaction.earn(loyalty_account_id=_account_id(),
                                        points_amount=Decimal("100"), operation_id=_op())
        reversal = LoyaltyTransaction.reversal_of(
            earn, operation_id=_op(), reason_code="ERROR_CAPTURA")
        assert reversal.transaction_type is TransactionType.REVERSAL
        assert reversal.points_amount == Decimal("-100")
        earn.mark_reversed(reversal.id)
        assert earn.status is TransactionStatus.REVERSED
        assert earn.reversal_transaction_id == reversal.id

    def test_cannot_reverse_an_already_reversed_transaction(self):
        earn = LoyaltyTransaction.earn(loyalty_account_id=_account_id(),
                                        points_amount=Decimal("100"), operation_id=_op())
        reversal = LoyaltyTransaction.reversal_of(earn, operation_id=_op(), reason_code="x")
        earn.mark_reversed(reversal.id)
        with pytest.raises(InvalidLoyaltyTransactionStateError):
            LoyaltyTransaction.reversal_of(earn, operation_id=_op(), reason_code="y")

    def test_reversal_requires_reason_code(self):
        earn = LoyaltyTransaction.earn(loyalty_account_id=_account_id(),
                                        points_amount=Decimal("100"), operation_id=_op())
        with pytest.raises(InvalidLoyaltyTransactionAmountError):
            LoyaltyTransaction.reversal_of(earn, operation_id=_op(), reason_code="")


class TestLoyaltyTransactionExpiry:
    def test_expire_of_is_negative(self):
        earn = LoyaltyTransaction.earn(loyalty_account_id=_account_id(),
                                        points_amount=Decimal("100"), operation_id=_op())
        expiry = LoyaltyTransaction.expire_of(
            earn, points_amount=Decimal("-100"), operation_id=_op())
        assert expiry.transaction_type is TransactionType.EXPIRE
        assert expiry.points_amount == Decimal("-100")
        earn.mark_expired()
        assert earn.status is TransactionStatus.EXPIRED

    def test_mark_expired_requires_available_status(self):
        earn = LoyaltyTransaction.earn(loyalty_account_id=_account_id(),
                                        points_amount=Decimal("100"), operation_id=_op())
        earn.mark_expired()
        with pytest.raises(InvalidLoyaltyTransactionStateError):
            earn.mark_expired()
