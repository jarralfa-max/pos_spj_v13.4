import unittest

from backend.domain.cash_register.exceptions import CashInvalidStateError
from backend.domain.cash_register.settlements import (
    CashSettlementClass, classify_settlement,
)


class CashSettlementClassificationTests(unittest.TestCase):
    def test_only_physical_cash_affects_drawer(self):
        self.assertTrue(classify_settlement("efectivo").affects_drawer)
        for settlement in (
            "LOYALTY_POINTS", "cupón", "vale", "saldo a favor",
            "tarjeta", "transferencia", "crédito", "Mercado Pago",
        ):
            self.assertFalse(classify_settlement(settlement).affects_drawer)

    def test_commercial_instruments_share_explicit_classification(self):
        for settlement in ("PUNTOS", "COUPON", "VOUCHER", "STORE_CREDIT"):
            self.assertIs(
                classify_settlement(settlement).classification,
                CashSettlementClass.COMMERCIAL_INSTRUMENT)

    def test_future_gift_card_is_classified_but_not_operational(self):
        with self.assertRaises(CashInvalidStateError):
            classify_settlement("GIFT_CARD")
        definition = classify_settlement("GIFT_CARD", allow_future=True)
        self.assertIs(definition.classification, CashSettlementClass.FUTURE_INSTRUMENT)
        self.assertFalse(definition.affects_drawer)
        self.assertFalse(definition.operational)

    def test_unknown_settlement_fails_closed(self):
        with self.assertRaises(CashInvalidStateError):
            classify_settlement("moneda mágica")


if __name__ == "__main__": unittest.main()
