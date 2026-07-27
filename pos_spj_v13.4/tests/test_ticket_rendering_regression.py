import base64
import io
import os
import sqlite3

from PIL import Image

from core.ticket_escpos_renderer import ALIGN_CENTER, ALIGN_RIGHT, GS, INIT, TicketESCPOSRenderer
from core.tickets.ticket_layout_config import TicketLayoutBlock, TicketLayoutConfig
from core.tickets.raffle_ticket_renderer import RaffleTicketESCPOSRenderer
from core.services.printer_service import PrinterService


def test_renderer_respects_block_order():
    cfg = TicketLayoutConfig(block_order=["totals", "items", "footer"], show_qr=False, show_barcode=False)
    cfg.blocks = {name: TicketLayoutBlock(enabled=True, order=i) for i, name in enumerate(cfg.block_order)}
    data = {"items": [{"nombre": "A", "cantidad": 1, "total": 2}], "totales": {"total_final": 2}, "layout_config": cfg.to_dict()}
    text = TicketESCPOSRenderer().render(data).decode("cp850", errors="ignore")
    assert text.index("TOTAL") < text.index("PRODUCTO")


def test_renderer_skips_disabled_blocks():
    cfg = TicketLayoutConfig(show_qr=False, show_barcode=False)
    cfg.blocks["items"].enabled = False
    data = {"items": [{"nombre": "NO_DEBE_SALIR", "cantidad": 1, "total": 2}], "totales": {"total_final": 2}, "layout_config": cfg.to_dict()}
    text = TicketESCPOSRenderer().render(data).decode("cp850", errors="ignore")
    assert "NO_DEBE_SALIR" not in text
    assert "TOTAL" in text


def test_renderer_prints_barcode_when_enabled():
    cfg = TicketLayoutConfig(show_barcode=True)
    cfg.blocks["barcode"].enabled = True
    data = {"folio": "V-123", "layout_config": cfg.to_dict()}
    assert GS + b"v0" in TicketESCPOSRenderer().render(data)


def test_renderer_does_not_print_barcode_when_disabled():
    cfg = TicketLayoutConfig(show_barcode=False)
    cfg.blocks["barcode"].enabled = True
    data = {"folio": "V-123", "layout_config": cfg.to_dict()}
    assert GS + b"v0" not in TicketESCPOSRenderer().render(data)


def test_barcode_block_uses_folio_when_no_barcode():
    cfg = TicketLayoutConfig(show_barcode=True)
    cfg.blocks["barcode"].enabled = True
    assert TicketESCPOSRenderer()._barcode_bytes({"folio": "V-123"}, 32)


def test_barcode_block_uses_codigo_barras_when_present():
    assert TicketESCPOSRenderer()._barcode_bytes({"codigo_barras": "ABC123"}, 32)


def test_barcode_not_rendered_when_show_barcode_false():
    cfg = TicketLayoutConfig(show_barcode=False)
    cfg.blocks["barcode"].enabled = True
    assert GS + b"v0" not in TicketESCPOSRenderer().render({"folio": "A", "layout_config": cfg.to_dict()})


def test_barcode_not_rendered_when_block_disabled():
    cfg = TicketLayoutConfig(show_barcode=True)
    cfg.blocks["barcode"].enabled = False
    assert GS + b"v0" not in TicketESCPOSRenderer().render({"folio": "A", "layout_config": cfg.to_dict()})


def test_renderer_prints_barcode_when_block_missing_but_show_barcode_enabled():
    data = {
        "folio": "V-MISSING-BLOCK",
        "layout_config": {
            "show_logo": False,
            "show_qr": False,
            "show_barcode": True,
            "blocks": {"items": {"enabled": True, "order": 4}},
        },
    }

    assert GS + b"v0" in TicketESCPOSRenderer().render(data)


def test_barcode_value_prefers_barcode_then_codigo_barras_then_folio():
    renderer = TicketESCPOSRenderer()

    assert renderer._barcode_value({"barcode": "BAR", "codigo_barras": "COD", "folio": "FOL"}) == "BAR"
    assert renderer._barcode_value({"codigo_barras": "COD", "folio": "FOL"}) == "COD"
    assert renderer._barcode_value({"folio": "FOL"}) == "FOL"


def test_barcode_raster_resets_printer_after_image():
    cfg = TicketLayoutConfig(show_barcode=True)
    cfg.blocks["barcode"].enabled = True
    out = TicketESCPOSRenderer().render({"folio": "V-RESET", "layout_config": cfg.to_dict()})

    assert GS + b"v0" in out
    assert INIT in out[out.index(GS + b"v0"):]

def test_renderer_respects_logo_size_and_alignment():
    img = Image.new("RGBA", (10, 10), (0, 0, 0, 255))
    buf = io.BytesIO(); img.save(buf, format="PNG")
    b64 = base64.b64encode(buf.getvalue()).decode()
    cfg = TicketLayoutConfig(logo_size="sm", logo_alignment="right", block_order=["logo"])
    cfg.blocks = {"logo": TicketLayoutBlock(enabled=True, order=0)}
    out = TicketESCPOSRenderer(paper_width_mm=58).render({"layout_config": cfg.to_dict()}, logo_b64=b64)
    assert ALIGN_RIGHT in out
    assert GS + b"v0" in out


def test_transparent_logo_background_becomes_white():
    img = Image.new("RGBA", (8, 8), (0, 0, 0, 0))
    img.putpixel((3, 3), (0, 0, 0, 255))
    buf = io.BytesIO(); img.save(buf, format="PNG")
    b64 = base64.b64encode(buf.getvalue()).decode()
    out = TicketESCPOSRenderer()._render_logo(b64, "md")
    assert out is not None
    # Raster header is 8 bytes. Polaridad ESC/POS GS v0: bit 1 = punto negro impreso.
    # El fondo transparente (→ blanco) NO debe imprimirse: bytes 0x00 mayoritarios;
    # sólo el pixel negro enciende bits. (Antes se enviaba invertido → fondo negro.)
    payload = out[8:]
    assert payload.count(b"\x00") > payload.count(b"\xff")


def test_logo_data_uri_transparent_background_becomes_white():
    img = Image.new("RGBA", (8, 1), (0, 0, 0, 0))
    img.putpixel((0, 0), (0, 0, 0, 255))
    buf = io.BytesIO(); img.save(buf, format="PNG")
    data_uri = "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()

    out = TicketESCPOSRenderer()._render_logo(data_uri, "md")

    assert out is not None
    # Pixel 0 negro → bit 1 (imprime, MSB); fondo blanco → bits 0. Polaridad correcta.
    assert out[8:] == bytes([0b10000000])


def test_logo_partial_alpha_antialias_does_not_create_black_background():
    img = Image.new("RGBA", (8, 1), (0, 0, 0, 0))
    img.putpixel((0, 0), (0, 0, 0, 255))
    img.putpixel((1, 0), (0, 0, 0, 64))
    buf = io.BytesIO(); img.save(buf, format="PNG")

    out = TicketESCPOSRenderer()._render_logo(base64.b64encode(buf.getvalue()).decode(), "md")

    assert out is not None
    # Pixel 0 negro → bit 1; pixel 1 (alfa 64, casi transparente → blanco) y el resto
    # del fondo → bits 0. El antialias no debe crear fondo negro.
    assert out[8:] == bytes([0b10000000])


def test_logo_alpha_diagnostic_enabled_by_layout_config(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    img = Image.new("RGBA", (8, 8), (0, 0, 0, 0))
    buf = io.BytesIO(); img.save(buf, format="PNG")
    b64 = base64.b64encode(buf.getvalue()).decode()
    cfg = TicketLayoutConfig(block_order=["logo"], ticket_debug_logo=True)
    cfg.blocks = {"logo": TicketLayoutBlock(enabled=True, order=0)}

    TicketESCPOSRenderer().render({"layout_config": cfg.to_dict()}, logo_b64=b64)

    assert (tmp_path / "logs" / "ticket_logo_input.png").exists()
    assert (tmp_path / "logs" / "ticket_logo_processed.png").exists()
    info = (tmp_path / "logs" / "ticket_logo_info.json").read_text(encoding="utf-8")
    assert '"had_alpha": true' in info

def test_logo_render_does_not_raise_on_invalid_base64():
    assert TicketESCPOSRenderer()._render_logo("not base64", "md") is None


def test_logo_size_md_for_58mm():
    img = Image.new("RGBA", (1000, 500), (0, 0, 0, 255))
    buf = io.BytesIO(); img.save(buf, format="PNG")
    b64 = base64.b64encode(buf.getvalue()).decode()
    out = TicketESCPOSRenderer(paper_width_mm=58)._render_logo(b64, "md")
    width_bytes = int.from_bytes(out[4:6], "little")
    height = int.from_bytes(out[6:8], "little")
    assert width_bytes * 8 <= 320
    assert height <= 140


def test_logo_alpha_diagnostic_disabled_by_default(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    img = Image.new("RGBA", (8, 8), (0, 0, 0, 0))
    buf = io.BytesIO(); img.save(buf, format="PNG")
    TicketESCPOSRenderer()._render_logo(base64.b64encode(buf.getvalue()).decode(), "md")
    assert not (tmp_path / "logs" / "ticket_logo_processed.png").exists()


def _product_db(with_unit=True):
    db = sqlite3.connect(":memory:")
    db.row_factory = sqlite3.Row
    unit_col = ", unidad TEXT" if with_unit else ""
    db.execute(f"CREATE TABLE productos(id INTEGER PRIMARY KEY, nombre TEXT{unit_col})")
    if with_unit:
        db.execute("INSERT INTO productos(id,nombre,unidad) VALUES(1,'Azucar','kg')")
    else:
        db.execute("INSERT INTO productos(id,nombre) VALUES(1,'Azucar')")
    return db


def test_ticket_item_uses_product_unit_when_payload_is_pza():
    svc = PrinterService(db_conn=_product_db()); svc.queue.stop()
    assert svc._hydrate_ticket_items([{"product_id": 1, "unidad": "pza"}])[0]["unidad"] == "kg"


def test_ticket_item_uses_product_unit_when_payload_is_pz():
    svc = PrinterService(db_conn=_product_db()); svc.queue.stop()
    assert svc._hydrate_ticket_items([{"product_id": 1, "unidad": "pz"}])[0]["unidad"] == "kg"


def test_ticket_item_preserves_specific_payload_unit_if_no_db_unit():
    svc = PrinterService(db_conn=_product_db(with_unit=False)); svc.queue.stop()
    assert svc._hydrate_ticket_items([{"product_id": 1, "unidad": "caja"}])[0]["unidad"] == "caja"


def test_ticket_item_does_not_crash_without_product_id():
    svc = PrinterService(db_conn=_product_db()); svc.queue.stop()
    assert svc._hydrate_ticket_items([{"nombre": "Libre", "unidad": "pza"}])[0]["nombre"] == "Libre"


def test_ticket_item_hydrates_product_name_and_unit_from_db():
    svc = PrinterService(db_conn=_product_db()); svc.queue.stop()
    item = svc._hydrate_ticket_items([{"product_id": 1, "unidad": "pza"}])[0]
    assert item["nombre"] == "Azucar"
    assert item["unidad"] == "kg"
    assert item["db_unidad"] == "kg"


def test_ticket_item_does_not_treat_sale_detail_id_as_product_id():
    db = sqlite3.connect(":memory:")
    db.row_factory = sqlite3.Row
    db.execute("CREATE TABLE productos(id INTEGER PRIMARY KEY, nombre TEXT, unidad TEXT)")
    db.execute("INSERT INTO productos(id,nombre,unidad) VALUES(99,'No debe usarse','kg')")
    svc = PrinterService(db_conn=db); svc.queue.stop()

    item = svc._hydrate_ticket_items([{
        "id": 99,
        "venta_id": 10,
        "nombre": "Linea libre",
        "unidad": "pza",
    }])[0]

    assert item["product_id"] == 0
    assert item["nombre"] == "Linea libre"
    assert item["unidad"] == "pza"
    assert item["db_unidad"] == ""


def test_ticket_item_hydrates_product_unit_by_barcode_when_product_id_missing():
    db = sqlite3.connect(":memory:")
    db.row_factory = sqlite3.Row
    db.execute("CREATE TABLE productos(id INTEGER PRIMARY KEY, nombre TEXT, unidad TEXT, codigo_barras TEXT)")
    db.execute("INSERT INTO productos(id,nombre,unidad,codigo_barras) VALUES(7,'Pollo a granel','kg','750001')")
    svc = PrinterService(db_conn=db); svc.queue.stop()

    item = svc._hydrate_ticket_items([{
        "barcode": "750001",
        "unidad": "PZA.",
    }])[0]

    assert item["product_id"] == 7
    assert item["producto_id"] == 7
    assert item["nombre"] == "Pollo a granel"
    assert item["unidad"] == "kg"
    assert item["unidad_producto"] == "kg"


def test_raffle_ticket_renderer_respects_block_order():
    cfg = TicketLayoutConfig.for_layout_type("raffle_ticket")
    cfg.block_order = ["ticket_number", "raffle_title"]
    cfg.blocks = {name: TicketLayoutBlock(enabled=True, order=i) for i, name in enumerate(cfg.block_order)}
    text = RaffleTicketESCPOSRenderer().render({"raffle_name": "Gran Sorteo", "numero_boleto": "1-2-1", "layout_config": cfg.to_dict()}).decode("cp850", errors="ignore")
    assert text.index("1-2-1") < text.index("Gran Sorteo")


def test_raffle_ticket_renderer_prints_ticket_number():
    text = RaffleTicketESCPOSRenderer().render({"numero_boleto": "1-2-1", "layout_config": TicketLayoutConfig.for_layout_type("raffle_ticket").to_dict()}).decode("cp850", errors="ignore")
    assert "1-2-1" in text


def test_raffle_ticket_renderer_prints_barcode_when_enabled():
    cfg = TicketLayoutConfig.for_layout_type("raffle_ticket")
    assert GS + b"v0" in RaffleTicketESCPOSRenderer().render({"numero_boleto": "1-2-1", "layout_config": cfg.to_dict()})


def test_raffle_ticket_renderer_prints_qr_when_enabled():
    cfg = TicketLayoutConfig.for_layout_type("raffle_ticket")
    assert GS + b"v0" in RaffleTicketESCPOSRenderer().render({"numero_boleto": "1-2-1", "qr_content": "QR", "layout_config": cfg.to_dict()})


def test_raffle_ticket_renderer_defaults_to_raffle_layout_without_layout_config():
    text = RaffleTicketESCPOSRenderer().render({"numero_boleto": "1-2-1", "raffle_name": "Sorteo"}).decode("cp850", errors="ignore")

    assert "BOLETO" in text
    assert "1-2-1" in text
    assert "Sorteo" in text


def test_raffle_ticket_renderer_compact_config_keeps_raffle_blocks():
    text = RaffleTicketESCPOSRenderer().render({
        "numero_boleto": "1-2-1",
        "layout_config": {"show_qr": False, "show_barcode": False},
    }).decode("cp850", errors="ignore")

    assert "BOLETO" in text
    assert "1-2-1" in text


def test_raffle_ticket_renderer_does_not_print_disabled_blocks():
    cfg = TicketLayoutConfig.for_layout_type("raffle_ticket")
    cfg.blocks["ticket_number"].enabled = False
    text = RaffleTicketESCPOSRenderer().render({"numero_boleto": "1-2-1", "layout_config": cfg.to_dict()}).decode("cp850", errors="ignore")
    assert "1-2-1" not in text


def test_printer_service_injects_ticket_debug_logo_config():
    db = sqlite3.connect(":memory:")
    db.row_factory = sqlite3.Row
    db.execute("CREATE TABLE configuraciones(clave TEXT PRIMARY KEY, valor TEXT)")
    db.execute("INSERT INTO configuraciones(clave, valor) VALUES('ticket_debug_logo', '1')")
    svc = PrinterService(db_conn=db); svc.queue.stop()

    prepared, _, _ = svc._prepare_ticket_data({"items": []})

    assert prepared["layout_config"]["ticket_debug_logo"] is True


def test_printer_service_injects_active_sale_ticket_layout():
    db = sqlite3.connect(":memory:"); db.row_factory = sqlite3.Row
    db.execute("CREATE TABLE configuraciones(clave TEXT PRIMARY KEY, valor TEXT)")
    cfg = TicketLayoutConfig(show_barcode=True)
    cfg.blocks["barcode"].enabled = True
    from core.tickets.ticket_layout_repository import TicketLayoutRepository
    TicketLayoutRepository(db_conn=db).save(cfg, layout_type="sale_ticket")
    svc = PrinterService(db_conn=db); svc.queue.stop()
    prepared, _, _ = svc._prepare_ticket_data({"folio": "V-1", "items": []})
    assert prepared["layout_config"]["show_barcode"] is True


def test_print_raffle_ticket_uses_raw_renderer_even_in_text_diagnostic_mode(monkeypatch, tmp_path):
    db = sqlite3.connect(":memory:"); db.row_factory = sqlite3.Row
    db.execute("CREATE TABLE configuraciones(clave TEXT PRIMARY KEY, valor TEXT)")
    svc = PrinterService(db_conn=db)
    svc._ticket_cfg = {
        "ubicacion": str(tmp_path / "raffle.prn"),
        "transport": "file",
        "encoding": "cp850",
        "print_logo": False,
        "print_qr": True,
        "escpos_mode": "text_diagnostic",
    }
    monkeypatch.setattr(svc, "validate_ticket_printer_config", lambda: type("VR", (), {"ok": True, "errors": []})())

    job_id = svc.print_raffle_ticket({"numero_boleto": "1-2-1"})

    try:
        assert job_id
        _, _, job = svc.queue._queue.get_nowait()
        assert job.job_type.value == "raffle_ticket"
        assert job.data.startswith(INIT)
        assert GS + b"v0" in job.data
        assert job.raw_data["qr_content"] == "1-2-1"
        assert job.raw_data["barcode"] == "1-2-1"
    finally:
        svc.queue.stop()


def test_print_raffle_ticket_loads_raffle_layout(monkeypatch, tmp_path):
    db = sqlite3.connect(":memory:"); db.row_factory = sqlite3.Row
    db.execute("CREATE TABLE configuraciones(clave TEXT PRIMARY KEY, valor TEXT)")
    cfg = TicketLayoutConfig.for_layout_type("raffle_ticket")
    cfg.show_barcode = False
    cfg.blocks["barcode"].enabled = False
    from core.tickets.ticket_layout_repository import TicketLayoutRepository
    TicketLayoutRepository(db_conn=db).save(cfg, layout_type="raffle_ticket")
    svc = PrinterService(db_conn=db)
    svc._ticket_cfg = {"ubicacion": str(tmp_path / "out.prn"), "transport": "file", "encoding": "cp850", "print_logo": True, "print_qr": True}
    monkeypatch.setattr(svc, "validate_ticket_printer_config", lambda: type("VR", (), {"ok": True, "errors": []})())
    job_id = svc.print_raffle_ticket({"numero_boleto": "1-2-1"})
    try:
        assert job_id
        _, _, job = svc.queue._queue.get_nowait()
        assert job.job_type.value == "raffle_ticket"
        assert job.raw_data["layout_config"]["show_barcode"] is False
    finally:
        svc.queue.stop()
