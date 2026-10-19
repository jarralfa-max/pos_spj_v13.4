from pathlib import Path
from tests.architecture.architecture_guardrails import APP_ROOT


def test_transfers_printing_has_no_ui_database_or_direct_printer_dependency():
    # Sólo los archivos de Transferencias: `infrastructure/printing/` aloja hoy
    # también el transporte ESC/POS y los renderizadores de Caja y Ventas, que
    # sí pueden hablar con la impresora (2026-10-16).
    printing = APP_ROOT / "backend/infrastructure/printing"
    files = [APP_ROOT / "backend/application/transfers/printing.py",
             printing / "transfers_print_gateway.py",
             printing / "transfer_document_renderer.py",
             printing / "picking_list_renderer.py",
             printing / "package_label_renderer.py",
             printing / "shipment_document_renderer.py",
             printing / "receipt_document_renderer.py"]
    source = "\n".join(path.read_text(encoding="utf-8") for path in files)
    for forbidden in ("sqlite3", "PyQt", "win32print", "escpos", "repositories."):
        assert forbidden not in source
    assert "TransfersPrintGateway" in source
    assert "TransferPrintAuditRepository" in source
    assert "original_print_id" in source
    assert "reprint_reason" in source
