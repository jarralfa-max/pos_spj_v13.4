"""
tests/test_production_query_service.py — FASE 9

Verifies ProductionQueryService functions:
  - get_daily_kpis: primary schema, legacy fallback, active lotes
  - get_recetas_list: product_recipes primary, recetas legacy fallback
  - get_recipe_components
  - get_historial_carnica
  - get_stock / get_stocks_for_products: inventario_actual primary, productos fallback
  - get_recetas_for_combo
  - Empty / missing-table robustness (no crash, returns empty/defaults)
"""
from __future__ import annotations

import sqlite3
import sys
import os

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.services.production_query_service import (
    get_daily_kpis,
    get_active_lotes_count,
    get_recetas_list,
    get_recipe_components,
    get_historial_carnica,
    get_stock,
    get_stocks_for_products,
    get_recetas_for_combo,
)


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture
def db():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    yield conn
    conn.close()


def _setup_modern_schema(conn: sqlite3.Connection):
    """Create production_batches + production_yield_analysis schema."""
    conn.executescript("""
        CREATE TABLE productos (id INTEGER PRIMARY KEY, nombre TEXT, unidad TEXT, existencia REAL DEFAULT 0, costo REAL DEFAULT 0);
        CREATE TABLE inventario_actual (producto_id INTEGER, sucursal_id INTEGER, cantidad REAL DEFAULT 0, costo_promedio REAL DEFAULT 0);

        CREATE TABLE production_batches (
            id TEXT PRIMARY KEY,
            source_product_id INTEGER,
            source_weight REAL DEFAULT 0,
            waste_weight REAL DEFAULT 0,
            estado TEXT DEFAULT 'abierto',
            branch_id INTEGER DEFAULT 1,
            closed_at TEXT
        );
        CREATE TABLE production_yield_analysis (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            batch_id TEXT,
            real_yield REAL DEFAULT 0
        );
        CREATE TABLE lotes (id INTEGER PRIMARY KEY, estado TEXT DEFAULT 'activo');

        CREATE TABLE product_recipes (
            id INTEGER PRIMARY KEY,
            nombre_receta TEXT,
            tipo_receta TEXT DEFAULT 'subproducto',
            product_id INTEGER,
            total_rendimiento REAL DEFAULT 0,
            rendimiento_esperado_pct REAL DEFAULT 0,
            is_active INTEGER DEFAULT 1,
            peso_promedio_kg REAL DEFAULT 1.0,
            unidad_base TEXT DEFAULT 'kg'
        );
        CREATE TABLE product_recipe_components (
            id INTEGER PRIMARY KEY,
            recipe_id INTEGER,
            component_product_id INTEGER,
            cantidad REAL DEFAULT 0,
            unidad TEXT DEFAULT 'kg',
            merma_pct REAL DEFAULT 0,
            rendimiento_pct REAL DEFAULT 0,
            orden INTEGER DEFAULT 0
        );

        CREATE TABLE recepciones_pollo (
            id INTEGER PRIMARY KEY,
            producto_id INTEGER,
            peso_bruto_kg REAL DEFAULT 0,
            merma_kg REAL DEFAULT 0,
            peso_neto_kg REAL DEFAULT 0,
            fecha_produccion TEXT,
            created_at TEXT
        );
    """)
    conn.commit()


def _setup_legacy_schema(conn: sqlite3.Connection):
    """Create legacy producciones + produccion_detalle + recetas schema."""
    conn.executescript("""
        CREATE TABLE productos (id INTEGER PRIMARY KEY, nombre TEXT, unidad TEXT, existencia REAL DEFAULT 0);
        CREATE TABLE inventario_actual (producto_id INTEGER, sucursal_id INTEGER, cantidad REAL DEFAULT 0);
        CREATE TABLE lotes (id INTEGER PRIMARY KEY, estado TEXT DEFAULT 'activo');

        CREATE TABLE producciones (
            id INTEGER PRIMARY KEY,
            estado TEXT DEFAULT 'completada',
            cantidad_base REAL DEFAULT 0,
            fecha TEXT
        );
        CREATE TABLE produccion_detalle (
            id INTEGER PRIMARY KEY,
            produccion_id INTEGER,
            tipo TEXT,
            cantidad_generada REAL DEFAULT 0
        );
        CREATE TABLE recetas (
            id INTEGER PRIMARY KEY,
            nombre TEXT,
            tipo_receta TEXT DEFAULT 'subproducto',
            producto_base_id INTEGER,
            rendimiento_esperado_pct REAL DEFAULT 0,
            activo INTEGER DEFAULT 1
        );
    """)
    conn.commit()


# ── get_daily_kpis ────────────────────────────────────────────────────────────

class TestGetDailyKpis:

    def test_returns_dict_with_required_keys(self, db):
        _setup_modern_schema(db)
        result = get_daily_kpis(db)
        for key in ("producciones_hoy", "kg_procesados", "merma_dia", "rendimiento", "lotes_activos"):
            assert key in result

    def test_zero_when_no_batches(self, db):
        _setup_modern_schema(db)
        result = get_daily_kpis(db)
        assert result["producciones_hoy"] == 0
        assert result["kg_procesados"] == 0.0

    def test_counts_closed_batches_today(self, db):
        _setup_modern_schema(db)
        db.execute("""
            INSERT INTO production_batches (id, source_weight, waste_weight, estado, closed_at)
            VALUES ('B1', 100.0, 10.0, 'cerrado', datetime('now'))
        """)
        db.execute("""
            INSERT INTO production_yield_analysis (batch_id, real_yield) VALUES ('B1', 90.0)
        """)
        db.commit()
        result = get_daily_kpis(db)
        assert result["producciones_hoy"] == 1
        assert abs(result["kg_procesados"] - 100.0) < 0.01
        assert abs(result["merma_dia"] - 10.0) < 0.01
        assert abs(result["rendimiento"] - 90.0) < 0.01

    def test_ignores_open_batches(self, db):
        _setup_modern_schema(db)
        db.execute("""
            INSERT INTO production_batches (id, source_weight, estado, closed_at)
            VALUES ('B2', 50.0, 'abierto', datetime('now'))
        """)
        db.commit()
        result = get_daily_kpis(db)
        assert result["producciones_hoy"] == 0

    def test_legacy_fallback_no_modern_tables(self, db):
        _setup_legacy_schema(db)
        db.execute("""
            INSERT INTO producciones (estado, cantidad_base, fecha)
            VALUES ('completada', 80.0, datetime('now'))
        """)
        db.execute("""
            INSERT INTO producciones (estado, cantidad_base, fecha)
            VALUES ('completada', 20.0, datetime('now'))
        """)
        db.execute("""
            INSERT INTO produccion_detalle (produccion_id, tipo, cantidad_generada)
            VALUES (1, 'merma', 8.0)
        """)
        db.commit()
        result = get_daily_kpis(db)
        assert result["producciones_hoy"] == 2
        assert abs(result["kg_procesados"] - 100.0) < 0.01
        assert abs(result["merma_dia"] - 8.0) < 0.01

    def test_lotes_activos_counted(self, db):
        _setup_modern_schema(db)
        db.execute("INSERT INTO lotes (estado) VALUES ('activo')")
        db.execute("INSERT INTO lotes (estado) VALUES ('activo')")
        db.execute("INSERT INTO lotes (estado) VALUES ('cerrado')")
        db.commit()
        result = get_daily_kpis(db)
        assert result["lotes_activos"] == 2

    def test_no_crash_empty_db(self, db):
        result = get_daily_kpis(db)
        assert isinstance(result, dict)
        assert result["producciones_hoy"] == 0


# ── get_active_lotes_count ────────────────────────────────────────────────────

class TestGetActiveLotesCount:

    def test_returns_zero_when_no_table(self, db):
        assert get_active_lotes_count(db) == 0

    def test_counts_active_only(self, db):
        _setup_modern_schema(db)
        db.execute("INSERT INTO lotes (estado) VALUES ('activo')")
        db.execute("INSERT INTO lotes (estado) VALUES ('cerrado')")
        db.commit()
        assert get_active_lotes_count(db) == 1


# ── get_recetas_list ──────────────────────────────────────────────────────────

class TestGetRecetasList:

    def test_returns_list(self, db):
        _setup_modern_schema(db)
        result = get_recetas_list(db)
        assert isinstance(result, list)

    def test_empty_when_no_recipes(self, db):
        _setup_modern_schema(db)
        assert get_recetas_list(db) == []

    def test_returns_recipe_rows(self, db):
        _setup_modern_schema(db)
        db.execute("INSERT INTO productos (id, nombre) VALUES (1, 'Pollo')")
        db.execute("""
            INSERT INTO product_recipes (id, nombre_receta, tipo_receta, product_id,
                total_rendimiento, is_active)
            VALUES (1, 'Despiece Pollo', 'subproducto', 1, 85.0, 1)
        """)
        db.execute("""
            INSERT INTO product_recipe_components (recipe_id, component_product_id, cantidad)
            VALUES (1, 1, 10.0), (1, 1, 5.0)
        """)
        db.commit()
        rows = get_recetas_list(db)
        assert len(rows) == 1
        r = rows[0]
        assert r["id"] == 1
        assert r["nombre"] == "Despiece Pollo"
        assert r["componentes"] == 2
        assert abs(r["rendimiento"] - 85.0) < 0.01

    def test_skips_inactive_recipes(self, db):
        _setup_modern_schema(db)
        db.execute("""
            INSERT INTO product_recipes (id, nombre_receta, is_active)
            VALUES (1, 'Activa', 1), (2, 'Inactiva', 0)
        """)
        db.commit()
        rows = get_recetas_list(db)
        assert len(rows) == 1
        assert rows[0]["nombre"] == "Activa"

    def test_legacy_fallback_used_when_modern_empty(self, db):
        _setup_legacy_schema(db)
        db.execute("INSERT INTO productos (id, nombre) VALUES (1, 'Res')")
        db.execute("""
            INSERT INTO recetas (id, nombre, tipo_receta, producto_base_id, activo)
            VALUES (1, 'Receta Legacy', 'subproducto', 1, 1)
        """)
        db.commit()
        rows = get_recetas_list(db)
        assert len(rows) == 1
        assert rows[0]["nombre"] == "Receta Legacy"
        assert rows[0]["componentes"] == 0


# ── get_recipe_components ─────────────────────────────────────────────────────

class TestGetRecipeComponents:

    def test_returns_empty_when_no_components(self, db):
        _setup_modern_schema(db)
        result = get_recipe_components(db, 999)
        assert result == []

    def test_returns_component_rows(self, db):
        _setup_modern_schema(db)
        db.execute("INSERT INTO productos (id, nombre, unidad) VALUES (1, 'Pechuga', 'kg')")
        db.execute("INSERT INTO productos (id, nombre, unidad) VALUES (2, 'Muslo', 'kg')")
        db.execute("""
            INSERT INTO product_recipe_components
                (recipe_id, component_product_id, cantidad, unidad, merma_pct, rendimiento_pct, orden)
            VALUES (1, 1, 5.0, 'kg', 2.0, 95.0, 1),
                   (1, 2, 3.0, 'kg', 1.5, 96.0, 2)
        """)
        db.commit()
        comps = get_recipe_components(db, 1)
        assert len(comps) == 2
        assert comps[0]["nombre"] == "Pechuga"
        assert abs(comps[0]["cantidad"] - 5.0) < 0.01
        assert abs(comps[0]["merma_pct"] - 2.0) < 0.01

    def test_no_crash_missing_table(self, db):
        result = get_recipe_components(db, 1)
        assert result == []


# ── get_historial_carnica ─────────────────────────────────────────────────────

class TestGetHistorialCarnica:

    def test_returns_empty_when_no_table(self, db):
        result = get_historial_carnica(db)
        assert result == []

    def test_returns_reception_rows(self, db):
        _setup_modern_schema(db)
        db.execute("INSERT INTO productos (id, nombre) VALUES (1, 'Pollo Entero')")
        db.execute("""
            INSERT INTO recepciones_pollo
                (producto_id, peso_bruto_kg, merma_kg, peso_neto_kg, fecha_produccion)
            VALUES (1, 100.0, 5.0, 95.0, '2025-01-01')
        """)
        db.commit()
        rows = get_historial_carnica(db)
        assert len(rows) == 1
        r = rows[0]
        assert r["producto"] == "Pollo Entero"
        assert abs(r["peso_bruto"] - 100.0) < 0.01
        assert abs(r["peso_neto"] - 95.0) < 0.01

    def test_respects_limit(self, db):
        _setup_modern_schema(db)
        for i in range(5):
            db.execute("""
                INSERT INTO recepciones_pollo (peso_bruto_kg, fecha_produccion)
                VALUES (10.0, '2025-01-0{i}')
            """.replace("{i}", str(i + 1)))
        db.commit()
        rows = get_historial_carnica(db, limit=3)
        assert len(rows) == 3


# ── get_stock / get_stocks_for_products ───────────────────────────────────────

class TestGetStock:

    def test_returns_zero_no_tables(self, db):
        assert get_stock(db, 1, 1) == 0.0

    def test_reads_inventario_actual(self, db):
        _setup_modern_schema(db)
        db.execute("""
            INSERT INTO inventario_actual (producto_id, sucursal_id, cantidad)
            VALUES (1, 1, 42.5)
        """)
        db.commit()
        assert abs(get_stock(db, 1, 1) - 42.5) < 0.001

    def test_falls_back_to_productos_existencia(self, db):
        _setup_modern_schema(db)
        db.execute("INSERT INTO productos (id, existencia) VALUES (1, 15.0)")
        db.commit()
        # No inventario_actual row → falls back to productos.existencia
        assert abs(get_stock(db, 1, 1) - 15.0) < 0.001

    def test_inventario_actual_takes_precedence(self, db):
        _setup_modern_schema(db)
        db.execute("INSERT INTO productos (id, existencia) VALUES (1, 15.0)")
        db.execute("INSERT INTO inventario_actual (producto_id, sucursal_id, cantidad) VALUES (1, 1, 30.0)")
        db.commit()
        assert abs(get_stock(db, 1, 1) - 30.0) < 0.001

    def test_get_stocks_for_products(self, db):
        _setup_modern_schema(db)
        db.execute("INSERT INTO inventario_actual (producto_id, sucursal_id, cantidad) VALUES (1, 1, 10.0)")
        db.execute("INSERT INTO inventario_actual (producto_id, sucursal_id, cantidad) VALUES (2, 1, 20.0)")
        db.commit()
        stocks = get_stocks_for_products(db, [1, 2, 3], 1)
        assert abs(stocks[1] - 10.0) < 0.001
        assert abs(stocks[2] - 20.0) < 0.001
        assert stocks[3] == 0.0


# ── get_recetas_for_combo ─────────────────────────────────────────────────────

class TestGetRecetasForCombo:

    def test_returns_empty_list_no_table(self, db):
        result = get_recetas_for_combo(db)
        assert isinstance(result, list)

    def test_returns_recipe_rows_with_expected_keys(self, db):
        _setup_modern_schema(db)
        db.execute("INSERT INTO productos (id, nombre, unidad) VALUES (1, 'Pollo', 'kg')")
        db.execute("""
            INSERT INTO product_recipes
                (id, nombre_receta, tipo_receta, product_id, peso_promedio_kg, is_active)
            VALUES (1, 'Despiece', 'subproducto', 1, 2.5, 1)
        """)
        db.commit()
        rows = get_recetas_for_combo(db)
        assert len(rows) == 1
        r = rows[0]
        for key in ("id", "nombre", "tipo_receta", "producto_base_id",
                    "peso_promedio_kg", "unidad_base", "prod_nombre", "prod_unidad"):
            assert key in r, f"Missing key: {key}"
        assert r["nombre"] == "Despiece"
        assert abs(r["peso_promedio_kg"] - 2.5) < 0.01
        assert r["prod_nombre"] == "Pollo"

    def test_excludes_inactive_recipes(self, db):
        _setup_modern_schema(db)
        db.execute("INSERT INTO product_recipes (id, nombre_receta, is_active) VALUES (1, 'A', 1)")
        db.execute("INSERT INTO product_recipes (id, nombre_receta, is_active) VALUES (2, 'B', 0)")
        db.commit()
        rows = get_recetas_for_combo(db)
        assert len(rows) == 1
        assert rows[0]["nombre"] == "A"
