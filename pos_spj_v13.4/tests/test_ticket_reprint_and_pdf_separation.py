from pathlib import Path


def _read(rel):
    return Path(rel).read_text(encoding='utf-8')


def test_reprint_uses_printerservice_and_not_pdf_fallback():
    src = _read('modulos/ventas.py')
    start = src.index('def _reimprimir_ultima_venta')
    end = src.index('def _guardar_pdf_auditoria_ultima_venta', start)
    fn = src[start:end]
    assert 'ps.print_ticket(datos_ticket)' in fn
    assert 'guardar_ticket_pdf' not in fn


def test_pdf_auditoria_is_separate_action():
    src = _read('modulos/ventas.py')
    assert 'def _guardar_pdf_auditoria_ultima_venta' in src
    start = src.index('def _guardar_pdf_auditoria_ultima_venta')
    fn = src[start:]
    assert 'self.guardar_ticket_pdf(ticket_data)' in fn


def test_pdf_can_be_generated_without_printer_check():
    src = _read('modulos/ventas.py')
    start = src.index('def _guardar_pdf_auditoria_ultima_venta')
    fn = src[start:]
    assert 'has_ticket_printer' not in fn
