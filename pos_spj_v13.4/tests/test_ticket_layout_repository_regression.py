import json
import sqlite3

from core.tickets.ticket_layout_config import TicketLayoutConfig, TicketLayoutBlock, RAFFLE_BLOCK_ORDER
from core.tickets.ticket_layout_repository import TicketLayoutRepository


def _db():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("CREATE TABLE configuraciones(clave TEXT PRIMARY KEY, valor TEXT)")
    return conn


def test_ticket_layout_repository_loads_active_ticket_layouts_sale_ticket():
    db = _db()
    repo = TicketLayoutRepository(db_conn=db)
    repo.ensure_schema()
    inactive = TicketLayoutConfig(show_qr=False)
    active = TicketLayoutConfig(show_qr=True, show_barcode=True)
    db.execute("INSERT INTO ticket_layouts(layout_type,nombre,config_json,activo) VALUES(?,?,?,0)", ("sale_ticket", "old", json.dumps(inactive.to_dict())))
    db.execute("INSERT INTO ticket_layouts(layout_type,nombre,config_json,activo) VALUES(?,?,?,1)", ("sale_ticket", "active", json.dumps(active.to_dict())))
    loaded = repo.load(layout_type="sale_ticket")
    assert loaded.show_qr is True
    assert loaded.show_barcode is True


def test_ticket_layout_repository_falls_back_to_configuraciones():
    db = _db()
    cfg = TicketLayoutConfig(paper_width_mm=58, show_qr=True)
    db.execute("INSERT INTO configuraciones(clave,valor) VALUES('ticket_layout_config',?)", (json.dumps(cfg.to_dict()),))
    loaded = TicketLayoutRepository(db_conn=db).load(layout_type="sale_ticket")
    assert loaded.paper_width_mm == 58
    assert loaded.show_qr is True


def test_ticket_layout_repository_falls_back_to_legacy():
    db = _db()
    db.executemany("INSERT INTO configuraciones(clave,valor) VALUES(?,?)", [
        ("ticket_paper_width", "58"), ("ticket_logo_pos", "Derecha"), ("ticket_qr_enabled", "1"), ("ticket_bc_enabled", "1")
    ])
    loaded = TicketLayoutRepository(db_conn=db).load(layout_type="sale_ticket")
    assert loaded.paper_width_mm == 58
    assert loaded.logo_alignment == "right"
    assert loaded.show_barcode is True


def test_ticket_layout_repository_supports_raffle_ticket():
    db = _db()
    loaded = TicketLayoutRepository(db_conn=db).load(layout_type="raffle_ticket")
    assert loaded.block_order == RAFFLE_BLOCK_ORDER
    assert loaded.show_barcode is True
    assert "ticket_number" in loaded.blocks


def test_ticket_layout_repository_save_activates_one_layout_per_type():
    db = _db()
    repo = TicketLayoutRepository(db_conn=db)
    repo.save(TicketLayoutConfig(show_qr=False), layout_type="sale_ticket")
    repo.save(TicketLayoutConfig(show_qr=True), layout_type="sale_ticket")
    repo.save(TicketLayoutConfig.for_layout_type("raffle_ticket"), layout_type="raffle_ticket")
    sale_active = db.execute("SELECT COUNT(*) FROM ticket_layouts WHERE layout_type='sale_ticket' AND activo=1").fetchone()[0]
    raffle_active = db.execute("SELECT COUNT(*) FROM ticket_layouts WHERE layout_type='raffle_ticket' AND activo=1").fetchone()[0]
    assert sale_active == 1
    assert raffle_active == 1
    assert repo.load("sale_ticket").show_qr is True
