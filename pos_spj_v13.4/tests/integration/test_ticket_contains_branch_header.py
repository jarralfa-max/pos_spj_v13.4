"""El ticket incluye datos reales de la sucursal (sin hardcodes ni default 1)."""
from __future__ import annotations

from backend.shared.ids import new_uuid
from core.engines.template_engine import TicketTemplateEngine
from core.services.sales_service import SalesService
from tests.integration._born_clean_db import make_db


class _CfgStub:
    def __init__(self, values):
        self._values = values

    def get(self, key, default=None):
        return self._values.get(key, default)


def _service(conn, cfg=None) -> SalesService:
    svc = object.__new__(SalesService)
    svc.db = conn
    svc.config_service = _CfgStub(cfg or {})
    return svc


def test_ticket_header_data_resolves_branch_by_uuid():
    conn = make_db()
    branch_id = new_uuid()
    conn.execute(
        "INSERT INTO sucursales (id, nombre, direccion, telefono) "
        "VALUES (?, 'Sucursal Norte', 'Calle 2 #45', '555-1234')",
        (branch_id,),
    )
    svc = _service(conn, {
        "nombre_empresa": "SPJ Carnes",
        "rfc": "SPJ010101XXX",
        "regimen_fiscal": "601",
        "whatsapp_empresa": "+5215550001111",
    })
    header = svc._ticket_header_data(branch_id)
    assert header["sucursal_id"] == branch_id
    assert header["sucursal_nombre"] == "Sucursal Norte"
    assert header["sucursal_direccion"] == "Calle 2 #45"
    assert header["sucursal_telefono"] == "555-1234"
    assert header["nombre_empresa"] == "SPJ Carnes"
    assert header["rfc_emisor"] == "SPJ010101XXX"


def test_missing_branch_leaves_fields_empty_without_failing():
    conn = make_db()
    svc = _service(conn)
    header = svc._ticket_header_data(new_uuid())   # sucursal inexistente
    assert header["sucursal_nombre"] == ""
    assert header["sucursal_direccion"] == ""
    header2 = svc._ticket_header_data("")          # sin sucursal — sin default '1'
    assert header2["sucursal_id"] == ""


def test_rendered_ticket_contains_branch_header():
    conn = make_db()
    branch_id = new_uuid()
    conn.execute(
        "INSERT INTO sucursales (id, nombre, direccion, telefono) "
        "VALUES (?, 'Sucursal Sur', 'Av. Tres 99', '555-9876')",
        (branch_id,),
    )
    svc = _service(conn, {"nombre_empresa": "SPJ Carnes"})
    datos = {
        "folio": "F-1",
        "fecha": "2026-07-12",
        "cajero": "luis",
        "totales": {"total_final": 50.0, "subtotal": 50.0},
        "items": [],
    }
    datos.update(svc._ticket_header_data(branch_id))
    html = TicketTemplateEngine(db_conn=conn).generar_ticket(
        SalesService._default_ticket_template(), datos
    )
    assert "Sucursal Sur" in html
    assert "Av. Tres 99" in html
    assert "555-9876" in html
    assert "San Bartolo" not in html