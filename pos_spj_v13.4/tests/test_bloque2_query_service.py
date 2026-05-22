# tests/test_bloque2_query_service.py — Bloque 2 tests
"""
Tests for ProductionQueryService new methods and existing methods
called by modulos/produccion.py after SQL extraction.

All tests use in-memory SQLite — no PyQt5, no filesystem.
"""
import sqlite3
import pytest
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import core.services.production_query_service as _pqs


# ── Schema helpers ────────────────────────────────────────────────────────────

def _make_db():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript("""
        CREATE TABLE productos (
            id      INTEGER PRIMARY KEY,
            nombre  TEXT,
            activo  INTEGER DEFAULT 1,
            unidad  TEXT DEFAULT 'kg',
            existencia REAL DEFAULT 0
        );
        CREATE TABLE inventario_actual (
            producto_id  INTEGER,
            sucursal_id  INTEGER,
            cantidad     REAL DEFAULT 0,
            PRIMARY KEY (producto_id, sucursal_id)
        );
        CREATE TABLE product_recipes (
            id                   INTEGER PRIMARY KEY,
            product_id           INTEGER,
            nombre_receta        TEXT,
            tipo_receta          TEXT DEFAULT 'subproducto',
            is_active            INTEGER DEFAULT 1,
            peso_promedio_kg     REAL DEFAULT 1.0,
            unidad_base          TEXT DEFAULT 'kg',
            total_rendimiento    REAL DEFAULT 0,
            rendimiento_esperado_pct REAL DEFAULT 0
        );
        CREATE TABLE product_recipe_components (
            id                  INTEGER PRIMARY KEY,
            recipe_id           INTEGER,
            component_product_id INTEGER,
            cantidad            REAL DEFAULT 0,
            unidad              TEXT DEFAULT 'kg',
            merma_pct           REAL DEFAULT 0,
            rendimiento_pct     REAL DEFAULT 0,
            orden               INTEGER DEFAULT 0
        );
        CREATE TABLE recepciones_pollo (
            id              INTEGER PRIMARY KEY,
            producto_id     INTEGER,
            peso_bruto_kg   REAL,
            merma_kg        REAL,
            peso_neto_kg    REAL,
            fecha_produccion TEXT,
            created_at      TEXT
        );
    """)
    return conn


# ── get_productos_activos ─────────────────────────────────────────────────────

class TestGetProductosActivos:
    def test_returns_active_only(self):
        conn = _make_db()
        conn.execute("INSERT INTO productos (id, nombre, activo) VALUES (1,'Pollo',1),(2,'Res',0)")
        rows = _pqs.get_productos_activos(conn)
        assert len(rows) == 1
        assert rows[0]["nombre"] == "Pollo"

    def test_returns_all_active(self):
        conn = _make_db()
        conn.executemany("INSERT INTO productos (id, nombre, activo) VALUES (?,?,1)",
                         [(1,"A"),(2,"B"),(3,"C")])
        rows = _pqs.get_productos_activos(conn)
        assert len(rows) == 3

    def test_empty_when_no_products(self):
        conn = _make_db()
        rows = _pqs.get_productos_activos(conn)
        assert rows == []

    def test_returns_id_and_nombre(self):
        conn = _make_db()
        conn.execute("INSERT INTO productos (id, nombre, activo) VALUES (42,'Cerdo',1)")
        rows = _pqs.get_productos_activos(conn)
        assert rows[0]["id"] == 42
        assert rows[0]["nombre"] == "Cerdo"

    def test_sorted_by_nombre(self):
        conn = _make_db()
        conn.executemany("INSERT INTO productos (id, nombre, activo) VALUES (?,?,1)",
                         [(1,"Zancas"),(2,"Alitas"),(3,"Pechuga")])
        rows = _pqs.get_productos_activos(conn)
        names = [r["nombre"] for r in rows]
        assert names == sorted(names)

    def test_graceful_on_missing_table(self):
        conn = sqlite3.connect(":memory:")  # no tables
        rows = _pqs.get_productos_activos(conn)
        assert rows == []


# ── get_receta_by_product_id ──────────────────────────────────────────────────

class TestGetRecetaByProductId:
    def test_finds_by_product_id_column(self):
        conn = _make_db()
        conn.execute("INSERT INTO productos (id, nombre) VALUES (5,'Pechuga')")
        conn.execute(
            "INSERT INTO product_recipes (id, product_id, nombre_receta, is_active) "
            "VALUES (10, 5, 'Receta Pechuga', 1)"
        )
        row = _pqs.get_receta_by_product_id(conn, 5)
        assert row is not None
        assert row["id"] == 10
        assert row["nombre_receta"] == "Receta Pechuga"

    def test_returns_none_when_not_found(self):
        conn = _make_db()
        row = _pqs.get_receta_by_product_id(conn, 99)
        assert row is None

    def test_returns_none_for_inactive_recipe(self):
        conn = _make_db()
        conn.execute(
            "INSERT INTO product_recipes (id, product_id, nombre_receta, is_active) "
            "VALUES (1, 7, 'Receta Inactiva', 0)"
        )
        row = _pqs.get_receta_by_product_id(conn, 7)
        assert row is None

    def test_returns_first_active_when_multiple(self):
        conn = _make_db()
        conn.executemany(
            "INSERT INTO product_recipes (id, product_id, nombre_receta, is_active) VALUES (?,?,?,?)",
            [(1, 5, "Primera", 1), (2, 5, "Segunda", 1)],
        )
        row = _pqs.get_receta_by_product_id(conn, 5)
        assert row is not None
        assert row["id"] in (1, 2)

    def test_treats_null_is_active_as_active(self):
        conn = _make_db()
        conn.execute(
            "INSERT INTO product_recipes (id, product_id, nombre_receta, is_active) "
            "VALUES (1, 3, 'Sin flag', NULL)"
        )
        row = _pqs.get_receta_by_product_id(conn, 3)
        assert row is not None

    def test_finds_by_base_product_id_column(self):
        """Schema variant: base_product_id instead of product_id."""
        conn = sqlite3.connect(":memory:")
        conn.executescript("""
            CREATE TABLE product_recipes (
                id               INTEGER PRIMARY KEY,
                base_product_id  INTEGER,
                nombre_receta    TEXT,
                is_active        INTEGER DEFAULT 1
            );
        """)
        conn.execute(
            "INSERT INTO product_recipes (id, base_product_id, nombre_receta, is_active) "
            "VALUES (20, 9, 'BOM Res', 1)"
        )
        row = _pqs.get_receta_by_product_id(conn, 9)
        assert row is not None
        assert row["id"] == 20
        assert row["nombre_receta"] == "BOM Res"

    def test_graceful_on_missing_table(self):
        conn = sqlite3.connect(":memory:")
        row = _pqs.get_receta_by_product_id(conn, 1)
        assert row is None


# ── get_stock (existing method — verify dict keys) ────────────────────────────

class TestGetStock:
    def test_returns_inventario_actual(self):
        conn = _make_db()
        conn.execute("INSERT INTO productos (id, nombre) VALUES (1,'P')")
        conn.execute("INSERT INTO inventario_actual VALUES (1, 1, 12.5)")
        qty = _pqs.get_stock(conn, 1, 1)
        assert qty == pytest.approx(12.5)

    def test_falls_back_to_productos_existencia(self):
        conn = _make_db()
        conn.execute("INSERT INTO productos (id, nombre, existencia) VALUES (1,'P', 7.0)")
        qty = _pqs.get_stock(conn, 1, 1)
        assert qty == pytest.approx(7.0)

    def test_returns_zero_when_no_rows(self):
        conn = _make_db()
        qty = _pqs.get_stock(conn, 99, 1)
        assert qty == 0.0

    def test_multi_branch_isolation(self):
        conn = _make_db()
        conn.execute("INSERT INTO productos (id, nombre) VALUES (1,'P')")
        conn.execute("INSERT INTO inventario_actual VALUES (1, 1, 10.0)")
        conn.execute("INSERT INTO inventario_actual VALUES (1, 2, 20.0)")
        assert _pqs.get_stock(conn, 1, 1) == pytest.approx(10.0)
        assert _pqs.get_stock(conn, 1, 2) == pytest.approx(20.0)


# ── get_stocks_for_products ───────────────────────────────────────────────────

class TestGetStocksForProducts:
    def test_returns_dict_keyed_by_product_id(self):
        conn = _make_db()
        conn.executemany("INSERT INTO productos (id, nombre) VALUES (?,?)", [(1,"A"),(2,"B")])
        conn.execute("INSERT INTO inventario_actual VALUES (1,1,5.0)")
        conn.execute("INSERT INTO inventario_actual VALUES (2,1,3.0)")
        stocks = _pqs.get_stocks_for_products(conn, [1, 2], 1)
        assert stocks == {1: pytest.approx(5.0), 2: pytest.approx(3.0)}

    def test_missing_product_returns_zero(self):
        conn = _make_db()
        stocks = _pqs.get_stocks_for_products(conn, [99], 1)
        assert stocks[99] == 0.0

    def test_empty_list(self):
        conn = _make_db()
        stocks = _pqs.get_stocks_for_products(conn, [], 1)
        assert stocks == {}


# ── get_historial_carnica ─────────────────────────────────────────────────────

class TestGetHistorialCarnica:
    def test_returns_empty_when_no_data(self):
        conn = _make_db()
        rows = _pqs.get_historial_carnica(conn)
        assert rows == []

    def test_returns_correct_keys(self):
        conn = _make_db()
        conn.execute("INSERT INTO productos (id, nombre) VALUES (1,'Res')")
        conn.execute(
            "INSERT INTO recepciones_pollo (id, producto_id, peso_bruto_kg, merma_kg, "
            "peso_neto_kg, fecha_produccion) VALUES (1, 1, 100.0, 5.0, 95.0, '2025-01-01')"
        )
        rows = _pqs.get_historial_carnica(conn)
        assert len(rows) == 1
        r = rows[0]
        assert "fecha" in r
        assert "producto" in r
        assert "peso_bruto" in r
        assert "merma" in r
        assert "peso_neto" in r
        assert r["peso_bruto"] == pytest.approx(100.0)
        assert r["merma"] == pytest.approx(5.0)
        assert r["peso_neto"] == pytest.approx(95.0)

    def test_limit_respected(self):
        conn = _make_db()
        conn.execute("INSERT INTO productos (id, nombre) VALUES (1,'P')")
        for i in range(10):
            conn.execute(
                "INSERT INTO recepciones_pollo (id, producto_id, peso_bruto_kg, merma_kg, "
                "peso_neto_kg) VALUES (?,1,1.0,0.0,1.0)", (i+1,)
            )
        rows = _pqs.get_historial_carnica(conn, limit=5)
        assert len(rows) <= 5


# ── get_recetas_list ──────────────────────────────────────────────────────────

class TestGetRecetasList:
    def test_returns_active_recipes(self):
        conn = _make_db()
        conn.execute("INSERT INTO productos (id, nombre) VALUES (1,'Pollo')")
        conn.execute(
            "INSERT INTO product_recipes (id, product_id, nombre_receta, is_active) "
            "VALUES (1, 1, 'Despiece Pollo', 1)"
        )
        rows = _pqs.get_recetas_list(conn)
        assert len(rows) == 1
        assert rows[0]["nombre"] == "Despiece Pollo"

    def test_excludes_inactive(self):
        conn = _make_db()
        conn.execute(
            "INSERT INTO product_recipes (id, product_id, nombre_receta, is_active) "
            "VALUES (1, 1, 'Inactiva', 0)"
        )
        rows = _pqs.get_recetas_list(conn)
        assert rows == []

    def test_returns_correct_keys(self):
        conn = _make_db()
        conn.execute("INSERT INTO productos (id, nombre) VALUES (1,'P')")
        conn.execute(
            "INSERT INTO product_recipes (id, product_id, nombre_receta, tipo_receta, "
            "is_active, total_rendimiento) VALUES (1, 1, 'R', 'subproducto', 1, 80.0)"
        )
        rows = _pqs.get_recetas_list(conn)
        r = rows[0]
        for key in ("id", "nombre", "tipo_receta", "producto_base", "rendimiento", "componentes"):
            assert key in r

    def test_component_count(self):
        conn = _make_db()
        conn.execute("INSERT INTO productos (id, nombre) VALUES (1,'P')")
        conn.execute(
            "INSERT INTO product_recipes (id, product_id, nombre_receta, is_active) "
            "VALUES (1, 1, 'R', 1)"
        )
        conn.executemany(
            "INSERT INTO product_recipe_components (id, recipe_id, component_product_id) VALUES (?,1,1)",
            [(1,),(2,),(3,)]
        )
        rows = _pqs.get_recetas_list(conn)
        assert rows[0]["componentes"] == 3


# ── get_recipe_components ─────────────────────────────────────────────────────

class TestGetRecipeComponents:
    def test_returns_empty_for_unknown_recipe(self):
        conn = _make_db()
        comps = _pqs.get_recipe_components(conn, 99)
        assert comps == []

    def test_returns_correct_fields(self):
        conn = _make_db()
        conn.execute("INSERT INTO productos (id, nombre) VALUES (1,'Pierna')")
        conn.execute(
            "INSERT INTO product_recipes (id, product_id, nombre_receta) VALUES (1,1,'R')"
        )
        conn.execute(
            "INSERT INTO product_recipe_components "
            "(id, recipe_id, component_product_id, cantidad, unidad, merma_pct, rendimiento_pct) "
            "VALUES (1, 1, 1, 2.5, 'kg', 3.0, 80.0)"
        )
        comps = _pqs.get_recipe_components(conn, 1)
        assert len(comps) == 1
        c = comps[0]
        assert c["nombre"] == "Pierna"
        assert c["cantidad"] == pytest.approx(2.5)
        assert c["unidad"] == "kg"
        assert c["merma_pct"] == pytest.approx(3.0)
        assert c["rendimiento_pct"] == pytest.approx(80.0)


# ── get_recetas_for_combo ─────────────────────────────────────────────────────

class TestGetRecetasForCombo:
    def test_returns_expected_keys(self):
        conn = _make_db()
        conn.execute("INSERT INTO productos (id, nombre, unidad) VALUES (1,'Pollo','kg')")
        conn.execute(
            "INSERT INTO product_recipes (id, product_id, nombre_receta, tipo_receta, "
            "is_active, peso_promedio_kg, unidad_base) VALUES (1,1,'Despiece','subproducto',1,2.0,'kg')"
        )
        rows = _pqs.get_recetas_for_combo(conn)
        assert len(rows) == 1
        for key in ("id", "nombre", "tipo_receta", "producto_base_id",
                    "peso_promedio_kg", "unidad_base", "prod_nombre", "prod_unidad"):
            assert key in rows[0]

    def test_only_active_recipes(self):
        conn = _make_db()
        conn.execute(
            "INSERT INTO product_recipes (id, product_id, nombre_receta, is_active) "
            "VALUES (1, 1, 'Activa', 1), (2, 1, 'Inactiva', 0)"
        )
        rows = _pqs.get_recetas_for_combo(conn)
        assert len(rows) == 1
        assert rows[0]["nombre"] == "Activa"


# ── get_daily_kpis ────────────────────────────────────────────────────────────

class TestGetDailyKpis:
    def test_returns_dict_with_required_keys(self):
        conn = _make_db()
        kpis = _pqs.get_daily_kpis(conn)
        for key in ("producciones_hoy", "kg_procesados", "merma_dia",
                    "rendimiento", "lotes_activos"):
            assert key in kpis

    def test_returns_zeros_when_no_data(self):
        conn = _make_db()
        kpis = _pqs.get_daily_kpis(conn)
        assert kpis["producciones_hoy"] == 0
        assert kpis["kg_procesados"] == 0.0
        assert kpis["lotes_activos"] == 0
