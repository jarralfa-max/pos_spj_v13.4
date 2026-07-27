"""Protection tests for QR-containers reads extracted from compras_pro.py."""

from __future__ import annotations

import sqlite3

import pytest

from backend.infrastructure.db.repositories.qr_containers_read_repository import (
    QrContainersReadRepository,
)


@pytest.fixture
def db():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript(
        """
        CREATE TABLE contenedores (
            id INTEGER PRIMARY KEY, codigo TEXT, tipo TEXT, descripcion TEXT,
            estado TEXT, fecha_creado TEXT, parent_id INTEGER, total REAL,
            folio_factura TEXT, comprador TEXT, proveedor_id INTEGER
        );
        CREATE TABLE proveedores (id INTEGER PRIMARY KEY, nombre TEXT);
        CREATE TABLE productos (id INTEGER PRIMARY KEY, nombre TEXT, unidad TEXT);
        CREATE TABLE contenedor_productos (
            contenedor_id INTEGER, producto_id INTEGER, cantidad REAL,
            costo_unitario REAL, cantidad_recibida REAL
        );
        INSERT INTO proveedores VALUES (1,'Carnes SA');
        INSERT INTO productos VALUES (7,'Pechuga','kg');
        INSERT INTO contenedores VALUES
            (1,'C-001','caja','principal','asignado','2026-06-02',NULL,500.0,'F-9','ana',1),
            (2,'C-002','caja','hijo','generado','2026-06-01',1,0,'', '',1);
        INSERT INTO contenedor_productos VALUES (1,7,10.0,50.0,8.0);
        """
    )
    conn.commit()
    return conn


@pytest.fixture
def repo(db):
    return QrContainersReadRepository(db)


def test_get_container_by_code(repo):
    c = repo.get_container_by_code("C-001")
    assert c["id"] == 1 and c["estado"] == "asignado"
    assert repo.get_container_by_code("nope") is None


def test_get_container_code(repo):
    assert repo.get_container_code(1) == "C-001"
    assert repo.get_container_code(999) is None


def test_list_child_containers(repo):
    kids = repo.list_child_containers(1)
    assert [k["codigo"] for k in kids] == ["C-002"]


def test_get_container_products_keys(repo):
    prods = repo.get_container_products(1)
    assert prods[0]["producto_id"] == 7
    assert prods[0]["nombre"] == "Pechuga" and prods[0]["unidad"] == "kg"


def test_get_container_for_reception_joins_supplier(repo):
    c = repo.get_container_for_reception("C-001")
    assert c["proveedor"] == "Carnes SA" and c["folio_factura"] == "F-9"


def test_products_for_reception_includes_recibida(repo):
    prods = repo.get_container_products_for_reception(1)
    assert prods[0]["recibida"] == 8.0


def test_search_excludes_self_by_code(repo):
    # searching 'C-0' should not return the exact-code match C-002 when excluded
    rows = repo.search_containers("C-0", exclude_codigo="C-002")
    ids = {r["id"] for r in rows}
    assert 2 not in ids and 1 in ids
