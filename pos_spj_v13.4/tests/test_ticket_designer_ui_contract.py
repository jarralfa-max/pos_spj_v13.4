from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _read(rel):
    return (ROOT / rel).read_text(encoding='utf-8')


def test_print_sample_calls_printer_service_not_qprinter():
    src = _read('modulos/ticket_designer.py')
    start = src.index('def _imprimir_muestra')
    fn = src[start:]
    assert 'printer_svc.print_ticket(' in fn
    assert 'printer_svc.print_raffle_ticket(' in fn
    assert 'QPrinter' not in fn


def test_ui_warns_html_is_preview_only_and_has_escpos_preview():
    src = _read('modulos/ticket_designer.py')
    assert 'La impresión térmica real usa ESC/POS RAW' in src
    assert 'Vista previa HTML (aproximada)' in src
    assert 'Preview monoespaciado ESC/POS' in src
    assert 'render_text_preview' in src
    assert 'Plantilla HTML (solo Preview/PDF avanzado)' in src
    assert '📦 Estructura' in src
    assert '🏷️ Marca' in src
    assert '🎯 Fidelidad' in src
    assert '🔥 FOMO / Promociones' in src
    assert '🖨️ Impresión ESC/POS' in src


def test_branding_message_uses_system_config_source():
    src = _read('modulos/ticket_designer.py')
    assert 'Usa logo de Configuración del Sistema como fuente principal.' in src


def test_raffle_layout_disables_sale_only_tabs_and_uses_raffle_preview_renderer():
    src = _read('modulos/ticket_designer.py')
    assert '_set_sale_only_tabs_enabled(not is_raffle)' in src
    assert 'RaffleTicketESCPOSRenderer' in src
    assert 'Número de boleto' in src
