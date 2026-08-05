import unittest
from datetime import date
from decimal import Decimal

from backend.domain.losses.expiry_damage import (
    DamageSeverity,
    ExpiryDamageRiskPolicy,
    LotRiskLevel,
)
from backend.domain.losses.exceptions import LossInvariantError


class ExpiryDamageRiskPolicyTest(unittest.TestCase):
    def setUp(self):
        self.policy = ExpiryDamageRiskPolicy()

    def test_expired_lot_is_critical(self):
        result = self.policy.assess(
            expiration_date="2026-08-02", as_of=date(2026, 8, 3),
            warning_days=7, critical_days=2, damage_severity=DamageSeverity.NONE,
            quantity=Decimal("3"), weight=Decimal("0"))
        self.assertIs(result.risk_level, LotRiskLevel.CRITICAL)
        self.assertEqual(result.days_to_expiry, -1)

    def test_major_damage_dominates_expiry_warning(self):
        result = self.policy.assess(
            expiration_date="2026-08-10", as_of=date(2026, 8, 3),
            warning_days=10, critical_days=2, damage_severity=DamageSeverity.MAJOR,
            quantity=Decimal("2"), weight=Decimal("1.25"))
        self.assertIs(result.risk_level, LotRiskLevel.HIGH)

    def test_float_is_rejected(self):
        with self.assertRaises(LossInvariantError):
            self.policy.assess(expiration_date=None,
                               damage_severity=DamageSeverity.MINOR,
                               quantity=1.5, weight=0)


if __name__ == "__main__":
    unittest.main()
