from pathlib import Path


def _read(rel: str) -> str:
    return Path(rel).read_text(encoding="utf-8")


def test_ticket_designer_print_sample_uses_printer_service():
    src = _read("modulos/ticket_designer.py")
    start = src.index("def _imprimir_muestra")
    fn = src[start:]
    assert "print_ticket(" in fn
    assert "QPrinter" not in fn
    assert "QPrintDialog" not in fn


def test_delivery_ticket_printer_service_no_qprinter_for_physical():
    src = _read("core/services/ticket_printer_service.py")
    assert "def _print_via_escpos" in src
    assert "QPrinter" not in src
    assert "doc.print_(" not in src
