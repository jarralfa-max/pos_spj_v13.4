"""BI-31 guardrails — responsive/touch/accessibility compliance for
`frontend/desktop/modules/business_intelligence/`. Encodes the findings of
the BI-31 audit (`docs/refactor/BI-31_responsive_touch_accessibility.md`)
so a future page can't silently regress them.
"""

from __future__ import annotations

import re
import sqlite3
from pathlib import Path

import pytest
from PyQt5.QtWidgets import QApplication

ROOT = Path(__file__).resolve().parents[2]
MODULE_DIR = ROOT / "frontend/desktop/modules/business_intelligence"


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


@pytest.fixture
def conn():
    connection = sqlite3.connect(":memory:")
    connection.execute(
        "CREATE TABLE ventas (id TEXT PRIMARY KEY, estado TEXT, fecha TEXT, sucursal_id TEXT)")
    connection.execute(
        "CREATE TABLE detalles_venta (id TEXT PRIMARY KEY, venta_id TEXT, producto_id TEXT, "
        "cantidad REAL, precio_unitario REAL)")
    connection.execute(
        "CREATE TABLE products (id TEXT PRIMARY KEY, code TEXT, name TEXT, short_name TEXT, "
        "product_type TEXT, base_unit_id TEXT, species_id TEXT, catch_weight_enabled INTEGER, "
        "lot_controlled INTEGER, inventory_managed INTEGER, sellable INTEGER, "
        "purchasable INTEGER, producible INTEGER, internal_only INTEGER, "
        "lifecycle_status TEXT)")
    connection.execute("CREATE TABLE sucursales (id TEXT PRIMARY KEY, nombre TEXT, activa INTEGER)")
    connection.execute(
        "CREATE TABLE product_cost (product_id TEXT, branch_id TEXT, average_cost REAL)")
    yield connection
    connection.close()


def _build_real_pages(conn):
    from frontend.desktop.modules.business_intelligence.business_intelligence_routes import (
        build_page,
    )
    page_ids = (
        "bi_executive", "bi_sales", "bi_inventory", "bi_purchasing", "bi_finance",
        "bi_forecast", "bi_recommendations", "bi_alerts", "bi_scenarios", "bi_reports",
    )
    return [build_page(page_id, conn) for page_id in page_ids]


def test_every_real_page_declares_an_accessible_name_and_description(qapp, conn):
    offenders = []
    for page in _build_real_pages(conn):
        if not page.accessibleName():
            offenders.append(f"{type(page).__name__}: missing accessibleName")
        if not page.accessibleDescription():
            offenders.append(f"{type(page).__name__}: missing accessibleDescription")
    assert not offenders


def test_no_raw_qpushbutton_construction_outside_the_canonical_factories():
    """Every button must come from `create_*_button` (touch height +
    accessible name are set there once, §31) — never a bare `QPushButton(`
    that would silently skip both."""
    offenders = []
    for path in MODULE_DIR.rglob("*.py"):
        source = path.read_text(encoding="utf-8")
        if re.search(r"(?<!create_)QPushButton\(", source):
            offenders.append(str(path.relative_to(ROOT)))
    assert not offenders


def test_no_fixed_size_widgets_outside_the_documented_collapsed_sidebar_rail():
    """`setFixedWidth`/`setFixedHeight` freeze a widget against responsive
    reflow — the one legitimate exception is the sidebar's collapsed
    icon-only rail (`business_intelligence_sidebar_widget.py`, mirrors
    `orders_delivery`'s own established pattern), which this test allows
    explicitly rather than by accident."""
    allowed = {"business_intelligence_sidebar_widget.py"}
    offenders = []
    for path in MODULE_DIR.rglob("*.py"):
        if path.name in allowed:
            continue
        source = path.read_text(encoding="utf-8")
        if "setFixedWidth" in source or "setFixedHeight" in source:
            offenders.append(str(path.relative_to(ROOT)))
    assert not offenders
