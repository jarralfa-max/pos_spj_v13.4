"""FASE 3 — Productos y proveedores: el picker de proveedores debe mostrar un
bloqueo financiero (migración 178) en vez de dejar que el usuario elija un
proveedor bloqueado y enterarse solo al fallar el envío."""

from __future__ import annotations

import sqlite3

import pytest

from backend.application.procurement.queries.direct_purchase_read_services import (
    SupplierPickerQueryService,
)
from frontend.desktop.modules.purchasing.direct_purchase_presenter import (
    _supplier_subtitle,
)


@pytest.fixture
def conn_without_migration_178():
    conn = sqlite3.connect(":memory:")
    conn.execute("CREATE TABLE proveedores(id TEXT PRIMARY KEY, nombre TEXT, activo INTEGER)")
    conn.execute("INSERT INTO proveedores VALUES ('s1','Proveedor Uno',1)")
    yield conn
    conn.close()


@pytest.fixture
def conn_with_migration_178():
    conn = sqlite3.connect(":memory:")
    conn.execute(
        "CREATE TABLE proveedores(id TEXT PRIMARY KEY, nombre TEXT, activo INTEGER,"
        " bloqueado_financiero INTEGER, compras_habilitadas INTEGER)")
    conn.execute("INSERT INTO proveedores VALUES ('s1','Proveedor Bloqueado',1,1,1)")
    conn.execute("INSERT INTO proveedores VALUES ('s2','Proveedor Normal',1,0,1)")
    yield conn
    conn.close()


def test_search_degrades_gracefully_without_migration_178_never_returns_empty(
        conn_without_migration_178):
    """Regression: an earlier version wrapped the swallowing `_query()` helper
    in a try/except that never triggered, so a missing column silently
    produced an empty result instead of falling back."""
    rows = SupplierPickerQueryService(conn_without_migration_178).search("Proveedor")
    assert [r["id"] for r in rows] == ["s1"]
    assert "bloqueado_financiero" not in rows[0]


def test_search_surfaces_financial_block_when_migrated(conn_with_migration_178):
    rows = SupplierPickerQueryService(conn_with_migration_178).search("Proveedor")
    by_id = {r["id"]: r for r in rows}
    assert by_id["s1"]["bloqueado_financiero"] == 1
    assert by_id["s2"]["bloqueado_financiero"] == 0


def test_supplier_subtitle_flags_blocked_and_disabled_suppliers():
    assert _supplier_subtitle({"bloqueado_financiero": 1}) == "Bloqueado financieramente"
    assert _supplier_subtitle({"compras_habilitadas": 0}) == "Compras deshabilitadas"
    assert _supplier_subtitle({"code": "PRV-1"}) == "PRV-1"
    assert _supplier_subtitle({}) == ""  # no migration yet — never invents a block
