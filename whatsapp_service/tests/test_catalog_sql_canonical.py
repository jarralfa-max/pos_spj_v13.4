"""PROD-22 — el catálogo de WhatsApp lee el maestro canónico, no `productos`.

En la base real `productos` (legacy) está vacía: el menú no encontraba nada. Se
prueba la consulta única `erp.catalog_sql` con el mismo criterio de precio que el
POS. El DDL es mínimo y propio: el microservicio no importa código del ERP.
"""

from __future__ import annotations

import sqlite3
from datetime import date, timedelta

import pytest

from decimal import Decimal

from whatsapp_service.erp.catalog_sql import (
    CATALOG_SELECT, OFFERABLE, catalog_params, catalog_row, product_category_name,
)

BRANCH = "suc-1"


@pytest.fixture
def db():
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    c.executescript("""
        CREATE TABLE products (id TEXT PRIMARY KEY, code TEXT, name TEXT, base_unit_id TEXT,
            category_id TEXT, lifecycle_status TEXT, sellable INTEGER, internal_only INTEGER);
        CREATE TABLE units_of_measure (id TEXT PRIMARY KEY, code TEXT);
        CREATE TABLE product_categories (id TEXT PRIMARY KEY, name TEXT);
        CREATE TABLE price_list (id TEXT PRIMARY KEY, kind TEXT, status TEXT, updated_at TEXT);
        CREATE TABLE product_price (id TEXT PRIMARY KEY, price_list_id TEXT, product_id TEXT,
            sale_price TEXT, branch_id TEXT, effective_from TEXT, effective_to TEXT);
        CREATE TABLE inventory_balances (id TEXT PRIMARY KEY, product_id TEXT, branch_id TEXT,
            quantity TEXT, reserved_quantity TEXT, inventory_status TEXT);
        INSERT INTO units_of_measure VALUES ('u-kg','KG');
        INSERT INTO product_categories VALUES ('c-pollo','Pollo');
        INSERT INTO price_list VALUES ('old','BASE','INACTIVE','2026-01-01');
        INSERT INTO price_list VALUES ('base','BASE','ACTIVE','2026-09-01');
    """)
    yield c
    c.close()


def _product(db, pid, name, *, status="ACTIVE", sellable=1, internal=0):
    db.execute("INSERT INTO products VALUES (?,?,?,?,?,?,?,?)",
               (pid, pid.upper(), name, "u-kg", "c-pollo", status, sellable, internal))


def _price(db, pid, amount, *, lista="base", branch="", desde=None, hasta=None):
    db.execute("INSERT INTO product_price VALUES (?,?,?,?,?,?,?)",
               (f"{pid}-{lista}-{branch}-{amount}", lista, pid, amount, branch, desde, hasta))


def _catalog(db):
    rows = db.execute(CATALOG_SELECT + f" WHERE {OFFERABLE} ORDER BY p.name",
                      catalog_params(BRANCH)).fetchall()
    return {r["nombre"]: catalog_row(r) for r in rows}


def test_offers_active_sellable_products_with_unit_and_category(db):
    _product(db, "p1", "Pechuga")
    _price(db, "p1", "115")
    item = _catalog(db)["Pechuga"]
    assert item["precio"] == 115 and item["unidad"] == "KG" and item["categoria"] == "Pollo"


def test_internal_draft_and_unsellable_products_are_not_offered(db):
    _product(db, "p1", "Canal en proceso", internal=1)
    _product(db, "p2", "Borrador", status="DRAFT")
    _product(db, "p3", "No vendible", sellable=0)
    assert _catalog(db) == {}


def test_price_uses_active_base_list_and_branch_override(db):
    _product(db, "p1", "Alas")
    _price(db, "p1", "999", lista="old")          # lista retirada: se ignora
    _price(db, "p1", "80")
    _price(db, "p1", "85", branch=BRANCH)         # el de la sucursal rige
    assert _catalog(db)["Alas"]["precio"] == 85


def test_expired_price_is_ignored(db):
    _product(db, "p1", "Molleja")
    ayer = (date.today() - timedelta(days=1)).isoformat()
    _price(db, "p1", "60", hasta=ayer)
    assert _catalog(db)["Molleja"]["precio"] == 0


def test_stock_is_available_minus_reserved_in_the_branch(db):
    _product(db, "p1", "Pierna")
    db.executescript("""
        INSERT INTO inventory_balances VALUES ('b1','p1','suc-1','10','2.5','AVAILABLE');
        INSERT INTO inventory_balances VALUES ('b2','p1','suc-1','4','0','QUARANTINE');
        INSERT INTO inventory_balances VALUES ('b3','p1','suc-2','50','0','AVAILABLE');
    """)
    stock = _catalog(db)["Pierna"]["stock"]
    assert stock == Decimal("7.5") and isinstance(stock, Decimal)


def test_category_name_lookup(db):
    _product(db, "p1", "Patas")
    assert product_category_name(db, "p1") == "Pollo"
    assert product_category_name(db, "no-existe") == ""
