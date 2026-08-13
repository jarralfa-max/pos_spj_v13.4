from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[2]


class CashPrintingBoundaryTests(unittest.TestCase):
    def test_cash_printing_has_renderers_queue_reprint_audit_and_no_ui_or_db(self):
        files = [
            ROOT / "backend/application/cash_register/printing.py",
            ROOT / "backend/infrastructure/printing/cash_register_renderers.py",
        ]
        source = "\n".join(path.read_text(encoding="utf-8") for path in files)
        for required in (
            "CashDocumentHtmlRenderer",
            "CashDocumentEscPosRenderer",
            "CashPrintQueue",
            "CashPrintJobStore",
            "DispatchCashPrintQueueUseCase",
            "CashPrintAuditRepository",
            "original_print_id",
            "reprint_reason",
            "cash_event_payload",
            "CASH_DOCUMENT_PRINTED",
            "OPENING",
            "BLIND_COUNT",
            "DIFFERENCE",
            "DEPOSIT_PREPARATION",
        ):
            self.assertIn(required, source)
        for forbidden in (
            "sqlite3",
            "PyQt",
            "QPrinter",
            "win32print",
            "commit(",
            "rollback(",
            "CREATE TABLE",
            "INSERT ",
            "SELECT ",
            "UPDATE ",
        ):
            self.assertNotIn(forbidden, source)


if __name__ == "__main__":
    unittest.main()
