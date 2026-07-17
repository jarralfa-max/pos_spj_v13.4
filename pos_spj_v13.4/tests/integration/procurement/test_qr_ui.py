"""PUR-13 step 2c UI — the enterprise QR + history tabs build and drive the
canonical flow through the presenter (no SQL in the widget). Headless."""

import os
import sqlite3

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PyQt5.QtWidgets")

from PyQt5.QtWidgets import QApplication  # noqa: E402

from backend.infrastructure.db.schema.procurement_schema import (  # noqa: E402
    create_procurement_schema,
)
from frontend.desktop.modules.purchasing.enterprise_routes import (  # noqa: E402
    build_enterprise_presenter,
)


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def conn():
    c = sqlite3.connect(":memory:")
    create_procurement_schema(c)
    c.execute("CREATE TABLE trazabilidad_qr (uuid_qr TEXT PRIMARY KEY, tipo TEXT,"
              " proveedor_id TEXT, sucursal_id TEXT, sucursal_destino TEXT, estado TEXT,"
              " datos_extra TEXT, fecha_generacion TEXT DEFAULT (datetime('now')),"
              " fecha_recepcion TEXT, recepcion_id TEXT)")
    c.execute("CREATE TABLE contenedores_qr (uuid_qr TEXT PRIMARY KEY, codigo_interno TEXT,"
              " descripcion TEXT, sucursal_origen TEXT, estado TEXT, sucursal_destino TEXT,"
              " viaje_actual INTEGER DEFAULT 0, created_at TEXT DEFAULT (datetime('now')),"
              " updated_at TEXT)")
    c.execute("CREATE TABLE proveedores (id TEXT PRIMARY KEY, nombre TEXT, rfc TEXT,"
              " activo INTEGER DEFAULT 1)")
    c.execute("CREATE TABLE sucursales (id TEXT PRIMARY KEY, nombre TEXT)")
    c.execute("CREATE TABLE recepciones (id TEXT PRIMARY KEY, uuid_qr TEXT, estado TEXT,"
              " created_at TEXT)")
    c.execute("INSERT INTO proveedores (id, nombre) VALUES ('s1','Proveedor 1')")
    c.commit()
    yield c
    c.close()


def test_enterprise_view_has_qr_and_history_tabs(app, conn):
    from frontend.desktop.modules.purchasing.enterprise_routes import (
        create_enterprise_purchasing_view,
    )
    view = create_enterprise_purchasing_view(conn)
    view.ensure_loaded()
    labels = [view._tabs.tabText(i) for i in range(view._tabs.count())]
    assert "Recepción QR" in labels and "Historial" in labels


def test_presenter_qr_generate_assign_flow(app, conn):
    p = build_enterprise_presenter(conn)
    ok, _m, data = p.generate_qr_label(description="Caja pollo")
    assert ok
    uuid_qr = data["uuid_qr"]
    assert any(c == uuid_qr for c in p.qr_available().row_ids)
    ok, _m, adata = p.assign_qr(
        uuid_qr=uuid_qr, supplier_id="s1", payment_condition="liquidado",
        items=[{"product_id": "p1", "quantity": "10", "unit_price": "30"}])
    assert ok and adata["total"] == "300"
    assert any(c == uuid_qr for c in p.qr_pending().row_ids)


def test_presenter_purchase_history_empty_graceful(app, conn):
    p = build_enterprise_presenter(conn)
    assert p.purchase_history().total == 0
