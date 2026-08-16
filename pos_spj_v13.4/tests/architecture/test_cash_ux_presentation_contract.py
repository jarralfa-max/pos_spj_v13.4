from pathlib import Path
import unittest


ROOT = Path(__file__).parents[2]
CASH_UI = ROOT / "frontend/desktop/modules/cash_register"
COMPONENTS = ROOT / "frontend/desktop/components"


class CashUxPresentationContractTests(unittest.TestCase):
    def test_sidebar_uses_task_language_not_ledger(self):
        source = (CASH_UI / "cash_register_routes.py").read_text(encoding="utf-8")
        self.assertIn('"Movimientos"', source)
        self.assertIn('"Mi turno"', source)
        self.assertNotIn('"Ledger"', source)
        self.assertNotIn('"Operacion"', source)

    def test_cash_dialogs_do_not_ask_operator_for_technical_ids(self):
        source = (CASH_UI / "cash_register_dialogs.py").read_text(encoding="utf-8")
        forbidden = (
            "UUID del reembolso",
            "UUID de la venta",
            "UUID de alcance",
            "Scope ID",
            "ISO-8601",
        )
        for text in forbidden:
            self.assertNotIn(text, source)

    def test_cash_pages_use_user_facing_error_mapper(self):
        pages = (
            "blind_count_page.py",
            "cash_configuration_page.py",
            "cash_devices_page.py",
            "cash_differences_page.py",
            "cash_handovers_page.py",
            "cash_ledger_page.py",
            "cash_notifications_page.py",
            "cash_operational_read_page.py",
            "cash_overview_page.py",
            "cash_refunds_page.py",
            "cash_shifts_page.py",
            "cash_sync_page.py",
            "cash_x_cuts_page.py",
            "cash_z_cuts_page.py",
        )
        for filename in pages:
            source = (CASH_UI / filename).read_text(encoding="utf-8")
            self.assertIn("user_facing_error", source)

    def test_cash_pages_do_not_present_print_or_shift_ids_in_cuts(self):
        for filename in ("cash_x_cuts_page.py", "cash_z_cuts_page.py"):
            source = (CASH_UI / filename).read_text(encoding="utf-8")
            self.assertIn("display_code(\"TUR\"", source)
            self.assertNotIn("Impresion en cola", source)

    def test_sensitive_workflows_use_semantic_dialogs(self):
        differences = (CASH_UI / "cash_differences_page.py").read_text(encoding="utf-8")
        handovers = (CASH_UI / "cash_handovers_page.py").read_text(encoding="utf-8")
        self.assertIn("ExplainCashDifferenceDialog", differences)
        self.assertIn("ResolveCashDifferenceDialog", differences)
        self.assertNotIn("CashTextReasonDialog", differences)
        self.assertIn("CashHandoverDenominationDialog", handovers)
        self.assertIn("DisputeCashHandoverDialog", handovers)
        self.assertNotIn("CashTextReasonDialog", handovers)
        devices = (CASH_UI / "cash_devices_page.py").read_text(encoding="utf-8")
        self.assertIn("CashDeviceActionDialog", devices)
        self.assertNotIn("CashTextReasonDialog", devices)
        shifts = (CASH_UI / "cash_shifts_page.py").read_text(encoding="utf-8")
        self.assertIn("SuspendCashShiftDialog", shifts)
        self.assertNotIn("CashTextReasonDialog", shifts)
        x_cuts = (CASH_UI / "cash_x_cuts_page.py").read_text(encoding="utf-8")
        z_cuts = (CASH_UI / "cash_z_cuts_page.py").read_text(encoding="utf-8")
        self.assertIn("ReprintCashDocumentDialog", x_cuts)
        self.assertIn("ReprintCashDocumentDialog", z_cuts)
        self.assertNotIn("CashTextReasonDialog", x_cuts)
        self.assertNotIn("CashTextReasonDialog", z_cuts)
        sync = (CASH_UI / "cash_sync_page.py").read_text(encoding="utf-8")
        self.assertIn("ResolveCashSyncConflictDialog", sync)
        self.assertNotIn("CashTextReasonDialog", sync)

    def test_common_inputs_expose_virtual_keyboard_affordance(self):
        for filename in ("text_inputs.py", "numeric_input.py"):
            source = (COMPONENTS / filename).read_text(encoding="utf-8")
            self.assertIn("attach_virtual_keyboard_action", source)
        search = (COMPONENTS / "search_input.py").read_text(encoding="utf-8")
        self.assertIn("StandardLineEdit", search)
        self.assertIn("keyboard_enabled=keyboard_enabled", search)


if __name__ == "__main__":
    unittest.main()
