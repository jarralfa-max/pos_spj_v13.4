"""Tests for Delivery product search refactor.

Verifies that NuevoPedidoDialog routes product search through ProductQueryService
(not raw SQL in UI), and that the backend product services are correct.
Uses source-text inspection to avoid importing PyQt5.
"""

from __future__ import annotations

import ast
import sqlite3
from pathlib import Path
from unittest.mock import MagicMock

import pytest

# ── Source-text checks (no PyQt5 import needed) ──────────────────────────────

_DELIVERY_SRC = Path(__file__).parent.parent / "modulos" / "delivery.py"
_DELIVERY_TEXT = _DELIVERY_SRC.read_text()


def test_delivery_imports_product_query_service():
    assert "from backend.application.queries.product_query_service import ProductQueryService" in _DELIVERY_TEXT


def test_delivery_imports_product_search_box():
    assert "from frontend.desktop.components.product_search_box import ProductSearchBox" in _DELIVERY_TEXT


def test_delivery_imports_search_option():
    assert "from frontend.desktop.components.search_selector import SearchOption" in _DELIVERY_TEXT


def test_delivery_no_raw_search_products_sql():
    """_do_prod_search with raw DeliveryQueryService call must not exist."""
    assert "_do_prod_search" not in _DELIVERY_TEXT


def test_delivery_no_lst_prod_sug_direct_sql():
    """lst_prod_sug QListWidget for product search must be removed."""
    assert "lst_prod_sug" not in _DELIVERY_TEXT


def test_delivery_uses_prod_search_widget():
    assert "self.prod_search = ProductSearchBox" in _DELIVERY_TEXT


def test_delivery_wires_selected_signal():
    assert "prod_search.selected.connect(self._on_product_selected)" in _DELIVERY_TEXT


def test_delivery_search_products_provider_method():
    assert "_search_products_provider" in _DELIVERY_TEXT


def test_delivery_on_product_selected_method():
    assert "_on_product_selected" in _DELIVERY_TEXT


def test_delivery_agregar_item_uses_prod_search_clear():
    assert "self.prod_search.clear()" in _DELIVERY_TEXT


def test_delivery_no_txt_prod_buscar_setText():
    """txt_prod_buscar direct mutation must not exist in product selection."""
    assert "txt_prod_buscar.setText" not in _DELIVERY_TEXT


# ── Backend service unit tests ────────────────────────────────────────────────

from backend.domain.services.product_type_policy import ProductTypePolicy, ProductTypeRules


def test_product_type_policy_has_all_seven_types():
    labels = ProductTypePolicy.type_labels_es()
    assert "Simple" in labels
    assert "Compuesto" in labels
    assert "Procesable" in labels
    assert "Subproducto" in labels
    assert "Producido" in labels
    assert "Insumo" in labels
    assert "Servicio" in labels


def test_product_type_policy_composite_rules():
    rules = ProductTypePolicy.rules_for("compuesto")
    assert rules.is_composite is True
    assert rules.allows_recipe is True
    assert rules.deducts_components_on_sale is True


def test_product_type_policy_insumo_not_sellable():
    rules = ProductTypePolicy.rules_for("insumo")
    assert rules.is_sellable is False


def test_product_type_policy_servicio_not_inventory_tracked():
    rules = ProductTypePolicy.rules_for("servicio")
    assert rules.is_inventory_tracked is False


def test_product_type_policy_normalize_from_spanish_label():
    canonical = ProductTypePolicy.canonical_from_label("Compuesto")
    assert canonical == "compuesto"


def test_product_type_policy_unknown_defaults_to_simple():
    canonical = ProductTypePolicy.canonical_from_label("XYZ_desconocido")
    assert canonical == "simple"


# ── ProductQueryService integration (SQLite in-memory) ───────────────────────

from backend.application.queries.product_query_service import ProductQueryService


@pytest.fixture()
def product_db():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute(
        """
        CREATE TABLE productos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nombre TEXT NOT NULL,
            codigo TEXT,
            codigo_barras TEXT,
            categoria TEXT,
            precio REAL DEFAULT 0,
            existencia REAL DEFAULT 0,
            unidad TEXT DEFAULT 'u',
            tipo_producto TEXT DEFAULT 'simple',
            activo INTEGER DEFAULT 1
        )
        """
    )
    conn.execute("INSERT INTO productos (nombre, codigo, precio, unidad, tipo_producto) VALUES ('Pollo asado', 'PA001', 89.5, 'kg', 'simple')")
    conn.execute("INSERT INTO productos (nombre, codigo, precio, unidad, tipo_producto) VALUES ('Jugo naranja', 'JN001', 25.0, 'L', 'simple')")
    conn.execute("INSERT INTO productos (nombre, codigo, precio, unidad, tipo_producto, activo) VALUES ('Inactivo', 'XX', 0, 'u', 'simple', 0)")
    conn.commit()
    return conn


def test_product_query_service_search_returns_results(product_db):
    svc = ProductQueryService.from_connection(product_db)
    results = svc.search_products("Pollo")
    assert len(results) == 1
    assert results[0].label == "Pollo asado"


def test_product_query_service_search_excludes_inactive(product_db):
    svc = ProductQueryService.from_connection(product_db)
    results = svc.search_products("Inactivo")
    assert len(results) == 0


def test_product_query_service_result_has_price_and_unit(product_db):
    svc = ProductQueryService.from_connection(product_db)
    results = svc.search_products("Jugo")
    assert len(results) == 1
    meta = results[0].metadata
    assert float(meta.get("price", 0)) == 25.0
    assert meta.get("unit") == "L"


def test_product_query_service_type_labels_es():
    svc = ProductQueryService(db_conn=None)
    labels = svc.type_labels_es()
    assert "Compuesto" in labels
    assert "Insumo" in labels
