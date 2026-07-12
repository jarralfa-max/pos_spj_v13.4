# tests/integration/test_ticket_contains_branch_header.py
"""El ticket debe incluir el encabezado de empresa + sucursal.

Valida:
- SalesService._ticket_header_data lee empresa (configuraciones) y sucursal
  (sucursales) usando branch_id UUID (str), sin default y sin int().
- El TicketTemplateEngine renderiza empresa, sucursal, dirección, teléfono,
  WhatsApp, RFC/régimen y folio/fecha/cajero/total.
"""
import sqlite3

import pytest

from backend.shared.ids import new_uuid


@pytest.fixture
def db():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    from migrations import engine
    engine.up(conn)
    conn.commit()
    return conn


def _config_service(db):
    from repositories.config_repository import ConfigRepository
    from core.services.config_service import ConfigService
    return ConfigService(ConfigRepository(db))


def _seed(db):
    bid = new_uuid()
    db.execute(
        "INSERT INTO sucursales (id,nombre,direccion,telefono,activa) VALUES (?,?,?,?,1)",
        (bid, "SPJ Centro", "Av. Reforma 123, CDMX", "55-1234-5678"),
    )
    for k, v in [
        ("nombre_empresa", "Super Pollo Juárez"),
        ("rfc", "SPJ010101ABC"),
        ("regimen_fiscal", "601 - General de Ley"),
        ("web_empresa", "www.spj.mx"),
        ("whatsapp_empresa", "+525599998888"),
    ]:
        db.execute("INSERT INTO configuraciones (clave,valor) VALUES (?,?)", (k, v))
    db.commit()
    return bid


def _sales_service(db, cfg):
    from core.services.sales_service import SalesService
    return SalesService(
        db, None, None, None, None, None, None, None,
        None, None, cfg, None,
    )


def test_ticket_header_data_desde_sucursal_y_config(db):
    bid = _seed(db)
    cfg = _config_service(db)
    svc = _sales_service(db, cfg)
    header = svc._ticket_header_data(str(bid))
    assert header["sucursal_id"] == bid            # UUID str, sin int()
    assert header["sucursal_nombre"] == "SPJ Centro"
    assert header["sucursal_direccion"] == "Av. Reforma 123, CDMX"
    assert header["sucursal_telefono"] == "55-1234-5678"
    assert header["nombre_empresa"] == "Super Pollo Juárez"
    assert header["rfc_emisor"] == "SPJ010101ABC"
    assert header["regimen_fiscal"] == "601 - General de Ley"
    assert header["whatsapp_empresa"] == "+525599998888"
    assert header["web_empresa"] == "www.spj.mx"


def test_ticket_header_sin_sucursal_no_falla_y_deja_vacio(db):
    cfg = _config_service(db)
    svc = _sales_service(db, cfg)
    # branch_id inexistente: no falla, deja sucursal vacía (no default 1)
    header = svc._ticket_header_data("no-existe")
    assert header["sucursal_id"] == "no-existe"
    assert header["sucursal_nombre"] == ""
    assert header["sucursal_direccion"] == ""
    assert header["sucursal_telefono"] == ""


def test_ticket_render_contiene_encabezado_completo(db):
    bid = _seed(db)
    cfg = _config_service(db)
    svc = _sales_service(db, cfg)
    header = svc._ticket_header_data(str(bid))

    venta_data = {
        "venta_id": "V-1001",
        "folio": "V-1001",
        "fecha": "2026-07-09 14:30:00",
        "cajero": "Ana",
        "totales": {"subtotal": 100.0, "descuento": 0.0, "total_final": 116.0},
        "items": [{"nombre": "Pollo", "cantidad": 1, "precio_unitario": 116.0, "total": 116.0}],
    }
    venta_data.update(header)

    from core.engines.template_engine import TicketTemplateEngine
    from modulos.ticket_designer import ModuloTicketDesigner  # noqa: F401 (asegura import)
    engine = TicketTemplateEngine(db)

    template = (
        "<div>{{nombre_empresa}} | Sucursal: {{sucursal_nombre}} | "
        "{{sucursal_direccion}} | Tel: {{sucursal_telefono}} | "
        "WA: {{whatsapp_empresa}} | RFC: {{rfc_emisor}} | Reg: {{regimen_fiscal}} | "
        "Ticket: {{folio}} | Fecha: {{fecha}} | Cajero: {{cajero}} | "
        "Total: {{total}} | {{items_html}}</div>"
    )
    html = engine.generar_ticket(template, venta_data)

    # empresa + sucursal + dirección + teléfono
    assert "Super Pollo Juárez" in html
    assert "SPJ Centro" in html
    assert "Av. Reforma 123, CDMX" in html
    assert "55-1234-5678" in html
    # whatsapp + fiscales
    assert "+525599998888" in html
    assert "SPJ010101ABC" in html
    assert "601 - General de Ley" in html
    # folio, fecha, cajero, total
    assert "V-1001" in html
    assert "2026-07-09 14:30:00" in html
    assert "Ana" in html
    assert "$116.00" in html
