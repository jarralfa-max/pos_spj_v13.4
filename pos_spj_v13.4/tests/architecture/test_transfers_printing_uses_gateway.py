from pathlib import Path
from tests.architecture.architecture_guardrails import APP_ROOT


def test_transfers_printing_has_no_ui_database_or_direct_printer_dependency():
    files = [(APP_ROOT / "backend/application/transfers/printing.py")]
    files += list((APP_ROOT / "backend/infrastructure/printing").glob("*.py"))
    source = "\n".join(path.read_text() for path in files)
    for forbidden in ("sqlite3", "PyQt", "win32print", "escpos", "repositories."):
        assert forbidden not in source
    assert "TransfersPrintGateway" in source
    assert "TransferPrintAuditRepository" in source
    assert "original_print_id" in source
    assert "reprint_reason" in source
