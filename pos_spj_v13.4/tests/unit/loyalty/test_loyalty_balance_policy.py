"""LOY-2 — LoyaltyBalancePolicy: balance reconstructed from the ledger
(master prompt §11, §26)."""

from __future__ import annotations

from decimal import Decimal

from backend.domain.loyalty.entities.loyalty_transaction import LoyaltyTransaction
from backend.domain.loyalty.policies.balance_policy import LoyaltyBalancePolicy
from backend.shared.ids import new_uuid


def _account_id() -> str:
    return new_uuid()


def _op() -> str:
    return new_uuid()


class TestLoyaltyBalancePolicy:
    def test_empty_ledger_has_zero_balance(self):
        assert LoyaltyBalancePolicy.balance([]) == Decimal("0")

    def test_earn_then_redeem(self):
        account = _account_id()
        earn = LoyaltyTransaction.earn(loyalty_account_id=account,
                                        points_amount=Decimal("100"), operation_id=_op())
        redeem = LoyaltyTransaction.redeem(loyalty_account_id=account,
                                            points_amount=Decimal("-40"), operation_id=_op())
        assert LoyaltyBalancePolicy.balance([earn, redeem]) == Decimal("60")

    def test_pending_transaction_is_excluded(self):
        account = _account_id()
        earn = LoyaltyTransaction.earn(loyalty_account_id=account,
                                        points_amount=Decimal("100"), operation_id=_op())
        pending = LoyaltyTransaction.earn(
            loyalty_account_id=account, points_amount=Decimal("50"), operation_id=_op(),
            available_at="2099-01-01T00:00:00+00:00")
        assert LoyaltyBalancePolicy.balance([earn, pending]) == Decimal("100")
        pending.mark_available()
        assert LoyaltyBalancePolicy.balance([earn, pending]) == Decimal("150")

    def test_reservation_reduces_balance_immediately(self):
        account = _account_id()
        earn = LoyaltyTransaction.earn(loyalty_account_id=account,
                                        points_amount=Decimal("100"), operation_id=_op())
        reservation = LoyaltyTransaction.reserve(
            loyalty_account_id=account, points_amount=Decimal("-30"), operation_id=_op())
        assert LoyaltyBalancePolicy.balance([earn, reservation]) == Decimal("70")
        assert LoyaltyBalancePolicy.reserved_amount([earn, reservation]) == Decimal("30")

    def test_releasing_a_reservation_restores_balance(self):
        account = _account_id()
        earn = LoyaltyTransaction.earn(loyalty_account_id=account,
                                        points_amount=Decimal("100"), operation_id=_op())
        reservation = LoyaltyTransaction.reserve(
            loyalty_account_id=account, points_amount=Decimal("-30"), operation_id=_op())
        release = LoyaltyTransaction.release_of(reservation, operation_id=_op())
        reservation.cancel_reservation()
        ledger = [earn, reservation, release]
        assert LoyaltyBalancePolicy.balance(ledger) == Decimal("100")
        assert LoyaltyBalancePolicy.reserved_amount(ledger) == Decimal("0")

    def test_consuming_a_reservation_does_not_change_balance_further(self):
        account = _account_id()
        earn = LoyaltyTransaction.earn(loyalty_account_id=account,
                                        points_amount=Decimal("100"), operation_id=_op())
        reservation = LoyaltyTransaction.reserve(
            loyalty_account_id=account, points_amount=Decimal("-30"), operation_id=_op())
        balance_while_reserved = LoyaltyBalancePolicy.balance([earn, reservation])
        reservation.mark_consumed()
        assert LoyaltyBalancePolicy.balance([earn, reservation]) == balance_while_reserved

    def test_reversal_nets_to_zero(self):
        account = _account_id()
        earn = LoyaltyTransaction.earn(loyalty_account_id=account,
                                        points_amount=Decimal("100"), operation_id=_op())
        reversal = LoyaltyTransaction.reversal_of(
            earn, operation_id=_op(), reason_code="ERROR_CAPTURA")
        earn.mark_reversed(reversal.id)
        assert LoyaltyBalancePolicy.balance([earn, reversal]) == Decimal("0")

    def test_expiry_reduces_balance_via_new_row(self):
        account = _account_id()
        earn = LoyaltyTransaction.earn(loyalty_account_id=account,
                                        points_amount=Decimal("100"), operation_id=_op())
        expiry = LoyaltyTransaction.expire_of(
            earn, points_amount=Decimal("-100"), operation_id=_op())
        earn.mark_expired()
        assert LoyaltyBalancePolicy.balance([earn, expiry]) == Decimal("0")

    def test_lifetime_earned_ignores_redemptions(self):
        account = _account_id()
        earn = LoyaltyTransaction.earn(loyalty_account_id=account,
                                        points_amount=Decimal("100"), operation_id=_op())
        bonus = LoyaltyTransaction.bonus(loyalty_account_id=account,
                                          points_amount=Decimal("20"), operation_id=_op())
        redeem = LoyaltyTransaction.redeem(loyalty_account_id=account,
                                            points_amount=Decimal("-40"), operation_id=_op())
        assert LoyaltyBalancePolicy.lifetime_earned([earn, bonus, redeem]) == Decimal("120")
