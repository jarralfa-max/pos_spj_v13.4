"""Protection tests for compras read SQL extracted from compras_pro.py."""

from __future__ import annotations

import sqlite3

import pytest

from backend.infrastructure.db.repositories.compras_read_repository import (
    ComprasReadRepository,
)


@pytest.fixture
def db():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript(
        """
        CREATE TABLE proveedores (id INTEGER PRIMARY KEY, nombre TEXT, activo INTEGER DEFAULT 1,
                                  rfc TEXT, telefono TEXT);
        CREATE TABLE sucursales (id INTEGER PRIMARY KEY, nombre TEXT, activo INTEGER DEFAULT 1);
        CREATE TABLE compras (id INTEGER PRIMARY KEY, folio TEXT, fecha TEXT, total REAL,
                             estado TEXT, proveedor_id INTEGER, sucursal_id INTEGER,
                             factura TEXT);
        INSERT INTO proveedores VALUES (1,'Carnes SA',1,'RFC1','555'),(2,'Inactivo',0,'','');
        INSERT INTO sucursales VALUES (1,'Centro',1),(2,'Cerrada',0);
        INSERT INTO compras (id,folio,fecha,total,estado,proveedor_id,sucursal_id,factura) VALUES
            (1,'C-1','2026-06-01',100.0,'credito',1,1,'F-1'),
            (2,'C-2','2026-06-02',200.0,'pagada',1,1,NULL),
            (3,'C-3','2026-06-03',300.0,'pendiente',1,1,NULL);

        CREATE TABLE configuraciones (clave TEXT, valor TEXT);
        CREATE TABLE inventario_actual (producto_id INTEGER, costo_promedio REAL);
        CREATE TABLE productos (id INTEGER PRIMARY KEY, nombre TEXT, unidad TEXT,
                                precio_compra REAL, codigo_interno TEXT, barcode TEXT);
        CREATE TABLE plantillas_compra (id INTEGER PRIMARY KEY, nombre TEXT);
        CREATE TABLE plantillas_compra_items (plantilla_id INTEGER, producto_id INTEGER,
                                              cantidad REAL, costo_unitario REAL);
        INSERT INTO configuraciones VALUES ('iva_rate','16');
        INSERT INTO inventario_actual VALUES (7, 42.5);
        INSERT INTO productos VALUES (7,'Pechuga','kg',60.0,'PCH','111');
        INSERT INTO plantillas_compra VALUES (1,'Semanal');
        INSERT INTO plantillas_compra_items VALUES (1,7,5.0,55.0);

        CREATE TABLE detalles_compra (compra_id INTEGER, producto_id INTEGER,
                                      cantidad REAL, precio_unitario REAL);
        CREATE TABLE purchase_requests (id INTEGER PRIMARY KEY, folio TEXT, estado TEXT,
                                        proveedor_nombre TEXT, total REAL, fecha_creacion TEXT,
                                        sucursal_id INTEGER, usuario TEXT, notas TEXT);
        CREATE TABLE ordenes_compra (id INTEGER PRIMARY KEY, folio TEXT, estado TEXT,
                                     proveedor_id INTEGER, total REAL, fecha_creacion TEXT,
                                     sucursal_id INTEGER, usuario TEXT, notas TEXT);
        CREATE TABLE recetas (id INTEGER PRIMARY KEY, producto_id INTEGER,
                              producto_base_id INTEGER, activa INTEGER, activo INTEGER);
        INSERT INTO detalles_compra VALUES (1,7,3.0,55.0);
        INSERT INTO purchase_requests VALUES (10,'PR-1','PENDIENTE_APROBACION','Carnes',100.0,'2026-06-01',1,'ana','x');
        INSERT INTO purchase_requests VALUES (11,'PR-2','CANCELADA','Carnes',50.0,'2026-06-02',1,'ana','y');
        INSERT INTO ordenes_compra VALUES (20,'PO-1','ABIERTA',1,200.0,'2026-06-01',1,'ana','z');
        INSERT INTO recetas VALUES (1,7,NULL,1,1);
        """
    )
    conn.commit()
    return conn


@pytest.fixture
def repo(db):
    return ComprasReadRepository(db)


def test_list_active_suppliers_excludes_inactive(repo):
    assert repo.list_active_suppliers() == [{"id": 1, "nombre": "Carnes SA"}]


def test_list_active_branches_excludes_inactive(repo):
    assert repo.list_active_branches() == [{"id": 1, "nombre": "Centro"}]


def test_get_supplier_returns_dict(repo):
    s = repo.get_supplier(1)
    assert s["nombre"] == "Carnes SA" and s["rfc"] == "RFC1"
    assert repo.get_supplier(999) is None


def test_recent_purchases_for_supplier_newest_first(repo):
    rows = repo.recent_purchases_for_supplier(1, 1, limit=5)
    assert [r[1] for r in rows] == ["C-3", "C-2", "C-1"]
    assert rows[0] == (3, "C-3", "2026-06-03", 300.0, "pendiente")


def test_cxp_pending_summary(repo):
    # only credito + pendiente count (100 + 300), not pagada
    assert repo.cxp_pending_summary(1, 1) == (2, 400.0)
    assert repo.cxp_pending_summary(1, 99) == (0, 0.0)


def test_get_config_value(repo):
    assert repo.get_config_value("iva_rate") == "16"
    assert repo.get_config_value("missing") is None


def test_get_avg_cost(repo):
    assert repo.get_avg_cost(7) == 42.5
    assert repo.get_avg_cost(999) == 0.0


def test_find_product_for_purchase(repo):
    p = repo.find_product_for_purchase("Pech")
    assert p["id"] == 7 and p["costo"] == 60.0
    assert repo.find_product_for_purchase("111")["id"] == 7  # barcode
    assert repo.find_product_for_purchase("zzz") is None


def test_list_purchase_templates(repo):
    assert repo.list_purchase_templates() == [{"id": 1, "nombre": "Semanal"}]


def test_get_template_items(repo):
    items = repo.get_template_items(1)
    assert items[0]["producto_id"] == 7 and items[0]["cantidad"] == 5.0
    assert items[0]["nombre"] == "Pechuga"


def test_get_supplier_name(repo):
    assert repo.get_supplier_name(1) == "Carnes SA"
    assert repo.get_supplier_name(999) is None


def test_get_purchase_for_reception(repo):
    p = repo.get_purchase_for_reception(1)
    assert p["folio"] == "C-1" and p["proveedor"] == "Carnes SA"
    assert repo.get_purchase_for_reception(999) is None


def test_get_purchase_items_for_reception(repo):
    items = repo.get_purchase_items_for_reception(1)
    assert items[0]["producto_id"] == 7 and items[0]["nombre"] == "Pechuga"
    assert items[0]["cantidad"] == 3.0


def test_list_purchase_requests_excludes_cancelled(repo):
    rows = repo.list_purchase_requests(1)
    assert [r["folio"] for r in rows] == ["PR-1"]  # CANCELADA excluded


def test_list_open_purchase_orders(repo):
    rows = repo.list_open_purchase_orders()
    assert rows[0]["folio"] == "PO-1"


def test_products_with_recipe(repo):
    assert repo.products_with_recipe([7, 99]) == {7}
    assert repo.products_with_recipe([]) == set()
