from decimal import Decimal
import unittest

from backend.domain.cash_register.difference_policy import CashDifferencePolicy
from backend.domain.cash_register.enums import (
    CashDifferenceClassification, CashDifferenceSeverity,
)


class CashDifferencePolicyTests(unittest.TestCase):
    def setUp(self):
        self.policy = CashDifferencePolicy(
            tolerance=Decimal("10"), critical_threshold=Decimal("100"),
            recurrence_threshold=3, channels=("IN_APP", "WHATSAPP"))

    def test_classifies_shortage_overage_and_tolerance(self):
        shortage = self.policy.evaluate(Decimal("-5"), recurrence_count=1)
        overage = self.policy.evaluate(Decimal("25"), recurrence_count=1)
        self.assertIs(shortage.classification, CashDifferenceClassification.SHORTAGE)
        self.assertIs(shortage.severity, CashDifferenceSeverity.WITHIN_TOLERANCE)
        self.assertFalse(shortage.alert_required)
        self.assertIs(overage.classification, CashDifferenceClassification.OVERAGE)
        self.assertIs(overage.severity, CashDifferenceSeverity.REVIEW)
        self.assertTrue(overage.alert_required)

    def test_amount_or_recurrence_escalates_to_critical(self):
        by_amount = self.policy.evaluate(Decimal("-100"), recurrence_count=1)
        recurrent = self.policy.evaluate(Decimal("15"), recurrence_count=3)
        self.assertIs(by_amount.severity, CashDifferenceSeverity.CRITICAL)
        self.assertIs(recurrent.severity, CashDifferenceSeverity.CRITICAL)
        self.assertIn("WHATSAPP", recurrent.channels)


if __name__ == "__main__": unittest.main()
