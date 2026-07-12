# tests/test_remediacion_c_born_clean_ddl.py
"""Remediación C (parte 2) — DDL runtime born-clean (DEEP_AUDIT B15).

`integrations/cfdi/cfdi_service.py` creaba facturas_cfdi con
`INTEGER PRIMARY KEY AUTOINCREMENT` en runtime y usaba lastrowid como
identidad; `integrations/delivery_pwa/pwa_server.py` creaba driver_locations
con PK entera. Ambas tablas nacen born-clean (TEXT PK) en m000, así que el DDL
runtime solo servía para contaminar la BD UUIDv7 y romper la identidad.
"""
from __future__ import annotations

import re
import sqlite3
import sys
from pathlib import Path

import pytest

PKG_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PKG_ROOT))

UUID_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-7[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$"
)


@pytest.fixture()
def born_clean_db():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    from migrations import m000_base_schema as m000
    m000.up(conn)
    return conn


# ── Funcional: CFDI nace con id UUID y timbra contra el schema born-clean ─────

def test_cfdi_insert_usa_uuid_y_timbrado_matchea(born_clean_db):
    conn = born_clean_db
    # Seed venta + detalle mínimos.
    conn.execute(
        "INSERT INTO ventas(id, folio, sucursal_id, usuario, total) "
        "VALUES (1,'V-1','B1','ana',116.0)"
    )
    conn.execute(
        "INSERT INTO detalles_venta(id, venta_id, producto_id, cantidad, precio_unitario, subtotal) "
        "VALUES ('d1',1,'p1',1,100.0,100.0)"
    )
    conn.commit()

    from integrations.cfdi.cfdi_service import CfdiService
    svc = CfdiService(conn)  # ya NO debe crear/alterar schema
    result = svc.generar_y_timbrar(1, {"rfc": "XAXX010101000", "nombre": "TEST"})

    assert result.get("ok"), f"timbrado falló: {result}"
    row = conn.execute(
        "SELECT id, estado FROM facturas_cfdi"
    ).fetchone()
    assert row is not None, "no se insertó la factura"
    # Identidad UUIDv7 (no NULL, no rowid entero).
    assert row["id"] and UUID_RE.match(str(row["id"])), (
        f"el id de facturas_cfdi no es UUIDv7: {row['id']!r}"
    )
    # El UPDATE de timbrado matcheó (con el bug lastrowid/NULL habría quedado 'pendiente').
    assert row["estado"] == "timbrada"
    assert result["factura_id"] == row["id"]


def test_cfdi_service_init_no_altera_pk_born_clean(born_clean_db):
    """Instanciar CfdiService no debe reintroducir una PK entera."""
    conn = born_clean_db
    from integrations.cfdi.cfdi_service import CfdiService
    CfdiService(conn)
    pk = [r for r in conn.execute("PRAGMA table_info(facturas_cfdi)") if r["pk"]]
    assert pk and pk[0]["type"].upper().startswith("TEXT"), (
        "facturas_cfdi debe conservar id TEXT PRIMARY KEY tras instanciar el servicio."
    )


def test_driver_locations_es_text_pk(born_clean_db):
    pk = [r for r in born_clean_db.execute("PRAGMA table_info(driver_locations)") if r["pk"]]
    assert pk and pk[0]["type"].upper().startswith("TEXT")


# ── Guardrails estáticos: sin DDL runtime / lastrowid / INTEGER PK ───────────

def _src(rel: str) -> str:
    return (PKG_ROOT / rel).read_text(encoding="utf-8")


def test_cfdi_service_sin_ddl_ni_lastrowid():
    src = _src("integrations/cfdi/cfdi_service.py")
    assert "CREATE TABLE" not in src, "B15: cfdi_service no debe crear schema en runtime."
    assert ".lastrowid" not in src, "B15: cfdi_service no debe usar lastrowid como identidad."
    assert "INTEGER PRIMARY KEY AUTOINCREMENT" not in src


def test_pwa_server_sin_ddl():
    src = _src("integrations/delivery_pwa/pwa_server.py")
    assert "CREATE TABLE" not in src, "B15: pwa_server no debe crear schema en runtime."
    assert "INTEGER PRIMARY KEY" not in src
