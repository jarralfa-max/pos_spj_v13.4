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
                             estado TEXT, proveedor_id INTEGER, sucursal_id INTEGER);
        INSERT INTO proveedores VALUES (1,'Carnes SA',1,'RFC1','555'),(2,'Inactivo',0,'','');
        INSERT INTO sucursales VALUES (1,'Centro',1),(2,'Cerrada',0);
        INSERT INTO compras VALUES (1,'C-1','2026-06-01',100.0,'credito',1,1);
        INSERT INTO compras VALUES (2,'C-2','2026-06-02',200.0,'pagada',1,1);
        INSERT INTO compras VALUES (3,'C-3','2026-06-03',300.0,'pendiente',1,1);
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
