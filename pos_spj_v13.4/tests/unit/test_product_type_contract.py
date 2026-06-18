"""
Tests — ProductQueryService.type_help_es / type_rules contract.

Verifica que la UI de DialogoProducto puede construirse sin AttributeError y
que el contrato entre productos.py y ProductQueryService es explícito y probado.

Tests:
 1.  type_labels_es returns non-empty list
 2.  type_help_es returns non-empty string for each label
 3.  type_rules returns dict with all required keys for each label
 4.  type_rules["allows_virtual_stock"] exists and is bool
 5.  type_help_es accepts canonical key (lowercase)
 6.  type_help_es accepts Spanish label (mixed case)
 7.  type_help_es unknown value falls back without raising
 8.  type_rules unknown value falls back to "simple"
 9.  ProductTypeRules.help_es is populated for every canonical type
10.  ProductTypeRules.allows_virtual_stock is populated for every canonical type
11.  ProductTypePolicy.rules_for returns correct type for "compuesto"
12.  ProductTypePolicy.rules_for returns correct type for "servicio"
13.  type_rules dict keys match ProductTypeRules fields
14.  type_help_es and type_rules agree on same canonical resolution
15.  No SQL executed by type_help_es
16.  No SQL executed by type_rules
17.  type_labels_es count equals number of canonical types
18.  Each label resolves back to its own canonical via normalize
19.  ProductQueryService.from_connection builds with all required methods
20.  All required methods exist on ProductQueryService (contract guard)
"""
from __future__ import annotations

import sqlite3

import pytest

from backend.application.queries.product_query_service import ProductQueryService
from backend.domain.services.product_type_policy import ProductTypePolicy, ProductTypeRules

# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture
def db():
    conn = sqlite3.connect(":memory:")
    conn.execute("""
        CREATE TABLE productos (
            id INTEGER PRIMARY KEY, nombre TEXT, codigo TEXT,
            codigo_barras TEXT, categoria TEXT, precio REAL, existencia REAL,
            activo INTEGER DEFAULT 1, unidad TEXT DEFAULT 'pza',
            tipo_producto TEXT DEFAULT 'simple', stock_minimo REAL DEFAULT 0
        )
    """)
    conn.commit()
    return conn


@pytest.fixture
def svc(db):
    return ProductQueryService.from_connection(db)


_ALL_CANONICAL = list(ProductTypePolicy._RULES.keys())
_ALL_LABELS    = ProductTypePolicy.type_labels_es()


# ── Tests 1-4: basic contract ─────────────────────────────────────────────────

def test_01_type_labels_es_returns_non_empty_list(svc):
    labels = svc.type_labels_es()
    assert isinstance(labels, list)
    assert len(labels) > 0


def test_02_type_help_es_returns_non_empty_string_for_each_label(svc):
    for label in _ALL_LABELS:
        help_text = svc.type_help_es(label)
        assert isinstance(help_text, str), f"help_es for '{label}' is not str"
        assert help_text.strip(), f"help_es for '{label}' is empty"


def test_03_type_rules_returns_dict_with_required_keys_for_each_label(svc):
    required = {
        "canonical", "label_es", "help_es",
        "is_composite", "is_byproduct", "allows_recipe", "allows_virtual_stock",
        "deducts_components_on_sale", "is_inventory_tracked", "is_sellable",
    }
    for label in _ALL_LABELS:
        rules = svc.type_rules(label)
        assert isinstance(rules, dict), f"type_rules('{label}') is not dict"
        missing = required - rules.keys()
        assert not missing, f"type_rules('{label}') missing keys: {missing}"


def test_04_type_rules_allows_virtual_stock_is_bool(svc):
    for label in _ALL_LABELS:
        rules = svc.type_rules(label)
        assert isinstance(rules["allows_virtual_stock"], bool), \
            f"allows_virtual_stock for '{label}' is not bool"


# ── Tests 5-8: input normalization ───────────────────────────────────────────

def test_05_type_help_es_accepts_canonical_key(svc):
    for key in _ALL_CANONICAL:
        help_text = svc.type_help_es(key)
        assert help_text.strip(), f"Empty help_es for canonical key '{key}'"


def test_06_type_help_es_accepts_spanish_label_mixed_case(svc):
    for label in _ALL_LABELS:
        # Mixed case should work
        assert svc.type_help_es(label.upper()).strip()
        assert svc.type_help_es(label.lower()).strip()


def test_07_type_help_es_unknown_value_falls_back_without_raising(svc):
    # Unknown type falls back to "simple" — must not raise AttributeError
    result = svc.type_help_es("tipo_que_no_existe_xyz")
    assert isinstance(result, str)
    assert result.strip()


def test_08_type_rules_unknown_value_falls_back_to_simple(svc):
    rules = svc.type_rules("tipo_desconocido_zzz")
    assert rules["canonical"] == "simple"


# ── Tests 9-10: ProductTypeRules fields populated ────────────────────────────

def test_09_product_type_rules_help_es_populated_for_every_canonical_type():
    for key, rules in ProductTypePolicy._RULES.items():
        assert isinstance(rules.help_es, str), f"help_es not str for '{key}'"
        assert rules.help_es.strip(), f"help_es empty for '{key}'"


def test_10_product_type_rules_allows_virtual_stock_is_bool_for_all():
    for key, rules in ProductTypePolicy._RULES.items():
        assert isinstance(rules.allows_virtual_stock, bool), \
            f"allows_virtual_stock not bool for '{key}'"


# ── Tests 11-12: specific type behavior ──────────────────────────────────────

def test_11_compuesto_rules_are_correct():
    rules = ProductTypePolicy.rules_for("compuesto")
    assert rules.is_composite is True
    assert rules.allows_recipe is True
    assert rules.deducts_components_on_sale is True
    assert rules.is_sellable is True


def test_12_servicio_rules_are_correct():
    rules = ProductTypePolicy.rules_for("servicio")
    assert rules.is_inventory_tracked is False
    assert rules.is_sellable is True


# ── Tests 13-14: dict ↔ dataclass consistency ────────────────────────────────

def test_13_type_rules_dict_keys_match_dataclass_fields(svc):
    import dataclasses
    field_names = {f.name for f in dataclasses.fields(ProductTypeRules)}
    for label in _ALL_LABELS:
        rules_dict = svc.type_rules(label)
        # Every dataclass field must be present in the dict
        for field in field_names:
            assert field in rules_dict, f"Field '{field}' missing in type_rules('{label}')"


def test_14_type_help_es_and_type_rules_agree_on_canonical(svc):
    for label in _ALL_LABELS:
        help_direct = svc.type_help_es(label)
        help_via_rules = svc.type_rules(label)["help_es"]
        assert help_direct == help_via_rules, \
            f"Mismatch for '{label}': type_help_es != type_rules['help_es']"


# ── Tests 15-16: no SQL in these methods ─────────────────────────────────────

class _SpyConnection:
    """Wraps sqlite3.Connection to track execute calls."""
    def __init__(self, conn):
        self._conn = conn
        self.executed: list[str] = []

    def execute(self, sql, *args, **kwargs):
        self.executed.append(sql)
        return self._conn.execute(sql, *args, **kwargs)

    def __getattr__(self, name):
        return getattr(self._conn, name)


def test_15_type_help_es_executes_no_sql(db):
    spy = _SpyConnection(db)
    svc = ProductQueryService.from_connection(spy)
    spy.executed.clear()           # discard any setup queries from from_connection
    svc.type_help_es("simple")
    assert not spy.executed, f"type_help_es executed SQL: {spy.executed}"


def test_16_type_rules_executes_no_sql(db):
    spy = _SpyConnection(db)
    svc = ProductQueryService.from_connection(spy)
    spy.executed.clear()
    svc.type_rules("simple")
    assert not spy.executed, f"type_rules executed SQL: {spy.executed}"


# ── Tests 17-18: label ↔ canonical round-trip ────────────────────────────────

def test_17_type_labels_es_count_equals_canonical_types():
    assert len(ProductTypePolicy.type_labels_es()) == len(ProductTypePolicy._RULES)


def test_18_each_label_resolves_back_to_its_canonical():
    for key, rules in ProductTypePolicy._RULES.items():
        resolved = ProductTypePolicy.normalize(rules.label_es)
        assert resolved == key, \
            f"Label '{rules.label_es}' resolved to '{resolved}', expected '{key}'"


# ── Tests 19-20: composition guard ───────────────────────────────────────────

def test_19_from_connection_builds_with_all_required_methods(db):
    svc = ProductQueryService.from_connection(db)
    assert callable(getattr(svc, "type_help_es", None))
    assert callable(getattr(svc, "type_rules", None))
    assert callable(getattr(svc, "type_labels_es", None))
    assert callable(getattr(svc, "list_categories", None))
    assert callable(getattr(svc, "get_product", None))
    assert callable(getattr(svc, "find_duplicate_name", None))


def test_20_missing_required_method_would_fail(db):
    """Guard: verifying the method exists is not enough — must also be callable.
    This test documents that a missing method raises AttributeError, not a
    silent failure hidden by hasattr/getattr tricks.
    """
    svc = ProductQueryService.from_connection(db)

    # Must not raise
    result = svc.type_help_es("simple")
    assert isinstance(result, str)

    # Confirm the old broken path would have raised
    class BrokenService:
        pass

    broken = BrokenService()
    with pytest.raises(AttributeError):
        broken.type_help_es("simple")  # type: ignore[attr-defined]
