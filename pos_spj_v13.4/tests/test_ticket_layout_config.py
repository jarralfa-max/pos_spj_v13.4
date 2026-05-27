from core.tickets.ticket_layout_config import TicketLayoutConfig


def test_default_layout_valid():
    cfg = TicketLayoutConfig()
    assert cfg.paper_width_mm == 80
    assert cfg.chars_per_line == 48
    assert "items" in cfg.block_order


def test_disable_logo():
    cfg = TicketLayoutConfig(show_logo=False)
    assert cfg.show_logo is False


def test_disable_fomo():
    cfg = TicketLayoutConfig(show_fomo=False)
    assert cfg.show_fomo is False


def test_change_block_order():
    order = ["logo", "items", "totals", "footer"]
    cfg = TicketLayoutConfig(block_order=order)
    assert cfg.block_order == order


def test_paper_width_58_and_80():
    assert TicketLayoutConfig(paper_width_mm=58).chars_per_line == 32
    assert TicketLayoutConfig(paper_width_mm=80).chars_per_line == 48


def test_legacy_migration_keys():
    cfg = TicketLayoutConfig.from_legacy_config(
        {
            "ticket_paper_width": "58",
            "ticket_logo_width": "170",
            "ticket_logo_pos": "Derecha",
            "ticket_qr_enabled": "1",
            "ticket_bc_enabled": "0",
        }
    )
    assert cfg.paper_width_mm == 58
    assert cfg.chars_per_line == 32
    assert cfg.logo_size == "170"
    assert cfg.logo_alignment == "right"
    assert cfg.show_qr is True
    assert cfg.show_barcode is False
