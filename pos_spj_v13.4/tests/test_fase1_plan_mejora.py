import sys, os, ast
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def test_printer_service_safe_baud_normaliza_invalidos():
    from core.services.printer_service import PrinterService
    assert PrinterService._safe_baud('9600') == 9600
    assert PrinterService._safe_baud('INVALID') == 9600
    assert PrinterService._safe_baud(999999) == 9600


def test_printer_service_resolve_transport_aliases_escpos():
    from core.services.printer_service import PrinterService, TransportType
    assert PrinterService._resolve_transport({'tipo': 'escpos_serial'}) == TransportType.SERIAL
    assert PrinterService._resolve_transport({'tipo': 'win32print'}) == TransportType.USB_WIN32
    assert PrinterService._resolve_transport({'tipo': 'escpos'}) == TransportType.AUTO


def test_print_transport_system_reusa_win32_ruta():
    from core.services.printer_service import PrintTransport, TransportType

    called = {'ok': False}

    def _fake_send_win32(data, destination):
        called['ok'] = True
        return True

    original = PrintTransport._send_win32
    PrintTransport._send_win32 = staticmethod(_fake_send_win32)
    try:
        ok = PrintTransport.send(b'x', TransportType.SYSTEM, 'TEST_PRINTER')
        assert ok is True
        assert called['ok'] is True
    finally:
        PrintTransport._send_win32 = original


def test_main_window_aplica_tooltips_globales_en_conectar():
    src = Path('interfaz/main_window.py').read_text(encoding='utf-8')
    tree = ast.parse(src)
    target = None
    for n in ast.walk(tree):
        if isinstance(n, ast.FunctionDef) and n.name == '_conectar':
            target = n
            break
    assert target is not None
    text = ast.get_source_segment(src, target) or ''
    assert 'apply_spj_tooltips' in text
