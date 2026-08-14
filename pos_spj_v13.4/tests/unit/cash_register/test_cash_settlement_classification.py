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
        for settlement in (
            "PUNTOS", "COUPON", "VOUCHER", "REFUND_VOUCHER",
            "STORE_CREDIT", "SALDO_PROMOCIONAL",
        ):
            definition = classify_settlement(settlement)
            self.assertIs(definition.classification, CashSettlementClass.COMMERCIAL_INSTRUMENT)
            self.assertTrue(definition.requires_external_validation)
            self.assertFalse(definition.affects_drawer)

    def test_operational_payment_methods_do_not_require_loyalty_validation(self):
        for settlement in ("CASH", "BANK_CARD", "BANK_TRANSFER", "CUSTOMER_CREDIT"):
            self.assertFalse(classify_settlement(settlement).requires_external_validation)

    def test_future_gift_card_is_classified_but_not_operational(self):
        with self.assertRaises(CashInvalidStateError):
            classify_settlement("GIFT_CARD")
        definition = classify_settlement("GIFT_CARD", allow_future=True)
        self.assertIs(definition.classification, CashSettlementClass.FUTURE_INSTRUMENT)
        self.assertFalse(definition.affects_drawer)
        self.assertFalse(definition.operational)
        self.assertTrue(definition.requires_external_validation)

    def test_unknown_settlement_fails_closed(self):
        with self.assertRaises(CashInvalidStateError):
            classify_settlement("moneda mágica")


if __name__ == "__main__": unittest.main()
