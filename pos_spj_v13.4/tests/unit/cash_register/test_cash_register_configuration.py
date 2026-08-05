from datetime import datetime, timezone
from decimal import Decimal
import unittest

from backend.domain.cash_register.configuration import (
    CashAlertRule, CashConfigurationResolver, CashDenomination,
    CashOperationLimit, CashPaymentMethod, CashPermissionProfile,
    CashScopedSetting, CashWhatsAppRecipient, ConfigurationScope,
)
from backend.shared.ids import new_uuid


NOW = datetime(2026, 8, 3, tzinfo=timezone.utc)


class CashConfigurationTests(unittest.TestCase):
    def test_hierarchy_uses_most_specific_active_setting(self):
        branch_id, register_id = new_uuid(), new_uuid()
        settings = [
            CashScopedSetting.create("blind_count_required", "true", ConfigurationScope.SYSTEM, None, NOW),
            CashScopedSetting.create("blind_count_required", "false", ConfigurationScope.BRANCH, branch_id, NOW),
            CashScopedSetting.create("blind_count_required", "true", ConfigurationScope.REGISTER, register_id, NOW),
        ]
        resolved = CashConfigurationResolver(settings).resolve(
            "blind_count_required", at=NOW,
            scope_ids={ConfigurationScope.BRANCH: branch_id, ConfigurationScope.REGISTER: register_id})
        self.assertEqual(resolved.value, "true")

    def test_expired_or_future_settings_do_not_apply(self):
        setting = CashScopedSetting.create("key", "value", ConfigurationScope.SYSTEM, None,
                                           datetime(2026, 8, 4, tzinfo=timezone.utc))
        self.assertIsNone(CashConfigurationResolver([setting]).resolve("key", at=NOW, scope_ids={}))

    def test_denominations_and_limits_are_decimal_only(self):
        denomination = CashDenomination.create("MXN", Decimal("200"), "Billete $200", 10)
        self.assertEqual(denomination.value, Decimal("200"))
        limit = CashOperationLimit.create("SAFE_DROP", Decimal("500"), Decimal("2000"))
        self.assertEqual(limit.hard_cap, Decimal("2000"))
        with self.assertRaises(TypeError):
            CashDenomination.create("MXN", 200.0, "Billete", 1)

    def test_payment_alert_whatsapp_and_permission_contracts(self):
        payment = CashPaymentMethod.create("CASH", "Efectivo", affects_physical_cash=True)
        alert = CashAlertRule.create("CASH_DIFFERENCE_DETECTED", "CRITICAL", ("IN_APP", "WHATSAPP"))
        recipient = CashWhatsAppRecipient.create("CASH_DIFFERENCE_DETECTED", "+525512345678")
        profile = CashPermissionProfile.create("Supervisor", ("CASH_Z_CUT_GENERATE", "CASH_DIFFERENCE_REVIEW"))
        self.assertTrue(payment.affects_physical_cash)
        self.assertIn("WHATSAPP", alert.channels)
        self.assertTrue(recipient.phone_e164.startswith("+52"))
        self.assertEqual(len(profile.permission_codes), 2)


if __name__ == "__main__":
    unittest.main()
