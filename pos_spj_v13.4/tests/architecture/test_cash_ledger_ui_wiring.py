from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[2]


class CashLedgerUiWiringArchitectureTests(unittest.TestCase):
    def test_cash_ledger_page_calls_presenter_commands_instead_of_orphan_signals(self):
        source = (
            ROOT / "frontend/desktop/modules/cash_register/cash_ledger_page.py"
        ).read_text(encoding="utf-8")
        self.assertNotIn("pyqtSignal", source)
        self.assertNotIn("movement_requested", source)
        self.assertNotIn("reversal_requested", source)
        self.assertIn("register_cash_movement(", source)
        self.assertIn("reverse_cash_movement(", source)
        self.assertIn("Ver detalle", source)
        self.assertIn("Abrir documento origen", source)
        self.assertIn("_show_selected_detail", source)
        self.assertIn("_open_origin_document", source)

    def test_cash_ledger_page_is_real_even_without_active_shift(self):
        workspace = (
            ROOT / "frontend/desktop/modules/cash_register/cash_register_workspace.py"
        ).read_text(encoding="utf-8")
        page = (
            ROOT / "frontend/desktop/modules/cash_register/cash_ledger_page.py"
        ).read_text(encoding="utf-8")
        self.assertIn('if key == "ledger" and query_service is not None:', workspace)
        self.assertIn("No hay turno activo seleccionado", page)
        self.assertIn("ViewState.EMPTY", page)

    def test_cash_movement_dialog_returns_decimal_not_float(self):
        source = (
            ROOT / "frontend/desktop/modules/cash_register/cash_register_dialogs.py"
        ).read_text(encoding="utf-8")
        self.assertIn("amount: Decimal", source)
        self.assertNotIn("float(self.amount.value())", source)
        self.assertIn("self.amount.decimal_value()", source)

    def test_cash_ledger_page_prompts_hot_authorization_when_backend_requires_it(self):
        source = (
            ROOT / "frontend/desktop/modules/cash_register/cash_ledger_page.py"
        ).read_text(encoding="utf-8")
        self.assertIn("CashAuthorizationRequiredError", source)
        self.assertIn('title="Autorizar movimiento"', source)
        self.assertIn("authorized_by=authorization.authorizer_user", source)
        self.assertGreaterEqual(source.count("register_cash_movement("), 2)

    def test_cash_safe_drop_uses_catalog_reason_code(self):
        page = (
            ROOT / "frontend/desktop/modules/cash_register/cash_ledger_page.py"
        ).read_text(encoding="utf-8")
        presenter = (
            ROOT / "frontend/desktop/modules/cash_register/cash_register_presenter.py"
        ).read_text(encoding="utf-8")
        factory = (
            ROOT / "backend/infrastructure/desktop/cash_register_factory.py"
        ).read_text(encoding="utf-8")
        self.assertIn('movement_reason_options("SAFE_DROP")', page)
        self.assertIn("reason_code=result.reason_code", page)
        self.assertIn("def movement_reason_options", presenter)
        self.assertIn("RegisterSafeDropUseCase", factory)
        self.assertIn('movement_type == CashMovementType.SAFE_DROP.value', factory)

    def test_cash_safe_drop_can_prepare_handover_with_denominations_from_ui(self):
        page = (
            ROOT / "frontend/desktop/modules/cash_register/cash_ledger_page.py"
        ).read_text(encoding="utf-8")
        presenter = (
            ROOT / "frontend/desktop/modules/cash_register/cash_register_presenter.py"
        ).read_text(encoding="utf-8")
        dialogs = (
            ROOT / "frontend/desktop/modules/cash_register/cash_register_dialogs.py"
        ).read_text(encoding="utf-8")
        factory = (
            ROOT / "backend/infrastructure/desktop/cash_register_factory.py"
        ).read_text(encoding="utf-8")

        self.assertIn("CashDenominationDialog", page)
        self.assertIn("prepare_cash_handover(", page)
        self.assertIn("denomination_options()", page)
        self.assertIn("def prepare_cash_handover", presenter)
        self.assertIn("def denomination_options", presenter)
        self.assertIn("class CashDenominationDialog", dialogs)
        self.assertIn("IntegerInput", dialogs)
        self.assertIn("PrepareTreasuryHandoverUseCase", factory)
        self.assertIn('"prepare_cash_handover"', factory)


if __name__ == "__main__":
    unittest.main()
