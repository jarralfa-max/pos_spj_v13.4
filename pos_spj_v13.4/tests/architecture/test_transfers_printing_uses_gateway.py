from pathlib import Path


def test_transfers_printing_has_no_ui_database_or_direct_printer_dependency():
    files = [Path("pos_spj_v13.4/backend/application/transfers/printing.py")]
    files += list(Path("pos_spj_v13.4/backend/infrastructure/printing").glob("*.py"))
    source = "\n".join(path.read_text() for path in files)
    for forbidden in ("sqlite3", "PyQt", "win32print", "escpos", "repositories."):
        assert forbidden not in source
    assert "TransfersPrintGateway" in source
    assert "TransferPrintAuditRepository" in source
    assert "original_print_id" in source
    assert "reprint_reason" in source
