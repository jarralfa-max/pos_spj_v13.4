from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _src():
    return (ROOT / "modulos" / "ticket_designer.py").read_text(encoding="utf-8")


def test_ticket_design_can_save_sale_ticket_layout():
    src = _src()
    assert '"sale_ticket"' in src
    assert 'save(cfg, layout_type=layout_type)' in src


def test_ticket_design_can_save_raffle_ticket_layout():
    src = _src()
    assert '"raffle_ticket"' in src
    assert 'Boleto de sorteo' in src
    assert 'raffle_ticket_template_html' in src


def test_ticket_design_does_not_mix_sale_and_raffle_blocks():
    src = _src()
    assert 'RAFFLE_BLOCK_ORDER if layout_type == "raffle_ticket" else DEFAULT_BLOCK_ORDER' in src
    assert 'cfg.show_loyalty = False; cfg.show_fomo = False' in src
    assert 'SALE_ONLY_BLOCKS = {"items", "totals", "payment", "loyalty", "fomo"}' in src
    assert 'RAFFLE_ONLY_BLOCKS = {"raffle_title", "ticket_number", "prize", "draw_date"}' in src


def test_ticket_design_loads_active_layout_by_type():
    src = _src()
    assert 'load(layout_type=self.current_layout_type)' in src
    assert 'self._on_layout_type_changed' in src


def test_ticket_design_exposes_raffle_blocks_and_footer_legal_controls():
    src = _src()
    for token in [
        '"raffle_title"',
        '"ticket_number"',
        '"prize"',
        '"draw_date"',
        'self.txt_footer_message',
        'self.txt_legal_message',
        'Bloques ESC/POS:',
    ]:
        assert token in src


def test_ticket_design_sample_print_uses_raffle_printer_for_raffle_layout():
    src = _src()
    start = src.index('def _imprimir_muestra')
    fn = src[start:]
    assert 'self.current_layout_type == "raffle_ticket"' in fn
    assert 'printer_svc.print_raffle_ticket(sample_ticket)' in fn
    assert 'printer_svc.print_ticket(sample_ticket)' in fn
