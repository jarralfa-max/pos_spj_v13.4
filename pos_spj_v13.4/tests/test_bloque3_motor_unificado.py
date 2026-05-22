# tests/test_bloque3_motor_unificado.py — Bloque 3 tests
"""
Tests for:
  A. ProductionEngine._get_receta_componentes()
       — canonical product_recipe_components first, legacy fallback.
  B. ProductionEngine._get_expected_yield_pct()
       — product_recipes first, recetas fallback.
  C. ProductionApplicationService.ejecutar_produccion()
       — dispatcher routes to RecipeEngine.
"""
import sqlite3
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

# ── Helpers ───────────────────────────────────────────────────────────────────

def _conn(schema_sql=""):
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    if schema_sql:
        conn.executescript(schema_sql)
    return conn


def _minimal_schema():
    return """
        CREATE TABLE productos (
            id INTEGER PRIMARY KEY, nombre TEXT, unidad TEXT DEFAULT 'kg', activo INTEGER DEFAULT 1
        );
        CREATE TABLE product_recipe_components (
            id INTEGER PRIMARY KEY,
            recipe_id            INTEGER,
            component_product_id INTEGER,
            rendimiento_pct      REAL DEFAULT 0,
            merma_pct            REAL DEFAULT 0,
            cantidad             REAL DEFAULT 0,
            unidad               TEXT DEFAULT 'kg',
            orden                INTEGER DEFAULT 0
        );
        CREATE TABLE product_recipes (
            id                      INTEGER PRIMARY KEY,
            product_id              INTEGER,
            nombre_receta           TEXT,
            tipo_receta             TEXT DEFAULT 'subproducto',
            is_active               INTEGER DEFAULT 1,
            rendimiento_esperado_pct REAL DEFAULT 0,
            merma_esperada_pct       REAL DEFAULT 0
        );
        CREATE TABLE receta_componentes (
            id                  INTEGER PRIMARY KEY,
            receta_id           INTEGER,
            producto_id         INTEGER,
            rendimiento_porcentaje REAL DEFAULT 0,
            merma_porcentaje    REAL DEFAULT 0,
            orden               INTEGER DEFAULT 0
        );
        CREATE TABLE recetas (
            id                      INTEGER PRIMARY KEY,
            nombre                  TEXT,
            rendimiento_esperado_pct REAL DEFAULT 0,
            merma_esperada_pct       REAL DEFAULT 0
        );
    """


def _make_engine(conn):
    """Build a ProductionEngine using a raw sqlite3 connection."""
    from core.production.production_engine import ProductionEngine
    from unittest.mock import MagicMock
    engine = ProductionEngine.__new__(ProductionEngine)
    # Minimal db wrapper: just exposes .execute()
    db = MagicMock()
    db.execute = lambda sql, params=(): conn.execute(sql, params)
    engine.db = db
    engine.branch_id = 1
    return engine


# ═══════════════════════════════════════════════════════════════════════════════
# A. ProductionEngine._get_receta_componentes()
# ═══════════════════════════════════════════════════════════════════════════════

class TestGetRecetaComponentes:

    def _engine_and_conn(self):
        conn = _conn(_minimal_schema())
        eng  = _make_engine(conn)
        return eng, conn

    def test_reads_from_canonical_product_recipe_components(self):
        eng, conn = self._engine_and_conn()
        conn.execute("INSERT INTO productos (id, nombre) VALUES (1,'Pechuga')")
        conn.execute(
            "INSERT INTO product_recipe_components "
            "(id, recipe_id, component_product_id, rendimiento_pct, merma_pct, orden) "
            "VALUES (1, 10, 1, 65.0, 2.0, 1)"
        )
        rows = eng._get_receta_componentes(conn, 10)
        assert len(rows) == 1
        r = rows[0]
        # Normalised aliases
        assert r["producto_id"] == 1
        assert r["prod_nombre"] == "Pechuga"
        assert r["rendimiento_porcentaje"] == pytest.approx(65.0)
        assert r["merma_porcentaje"] == pytest.approx(2.0)

    def test_returns_multiple_components(self):
        eng, conn = self._engine_and_conn()
        conn.executemany(
            "INSERT INTO productos (id, nombre) VALUES (?,?)",
            [(1,"Pechuga"),(2,"Pierna"),(3,"Ala")]
        )
        conn.executemany(
            "INSERT INTO product_recipe_components "
            "(id, recipe_id, component_product_id, rendimiento_pct, orden) "
            "VALUES (?,10,?,?,?)",
            [(1,1,50.0,1),(2,2,30.0,2),(3,3,15.0,3)]
        )
        rows = eng._get_receta_componentes(conn, 10)
        assert len(rows) == 3
        pcts = [r["rendimiento_porcentaje"] for r in rows]
        assert 50.0 in pcts
        assert 30.0 in pcts

    def test_returns_empty_for_unknown_recipe(self):
        eng, conn = self._engine_and_conn()
        rows = eng._get_receta_componentes(conn, 999)
        assert rows == []

    def test_falls_back_to_legacy_when_canonical_empty(self):
        """When product_recipe_components has no rows, use receta_componentes."""
        eng, conn = self._engine_and_conn()
        conn.execute("INSERT INTO productos (id, nombre) VALUES (1,'Pierna')")
        conn.execute(
            "INSERT INTO receta_componentes "
            "(id, receta_id, producto_id, rendimiento_porcentaje, merma_porcentaje, orden) "
            "VALUES (1, 5, 1, 40.0, 3.0, 1)"
        )
        rows = eng._get_receta_componentes(conn, 5)
        assert len(rows) == 1
        # Legacy rows are returned as-is (dict from sqlite Row)
        assert rows[0]["producto_id"] == 1
        assert rows[0]["rendimiento_porcentaje"] == pytest.approx(40.0)
        assert rows[0]["merma_porcentaje"] == pytest.approx(3.0)

    def test_canonical_takes_priority_over_legacy(self):
        """When canonical has rows, legacy is ignored even if it also has data."""
        eng, conn = self._engine_and_conn()
        conn.execute("INSERT INTO productos (id, nombre) VALUES (1,'P')")
        # Canonical row
        conn.execute(
            "INSERT INTO product_recipe_components "
            "(id, recipe_id, component_product_id, rendimiento_pct) VALUES (1, 7, 1, 88.0)"
        )
        # Legacy row (different pct — should not be returned)
        conn.execute(
            "INSERT INTO receta_componentes (id, receta_id, producto_id, rendimiento_porcentaje) "
            "VALUES (1, 7, 1, 50.0)"
        )
        rows = eng._get_receta_componentes(conn, 7)
        assert len(rows) == 1
        assert rows[0]["rendimiento_porcentaje"] == pytest.approx(88.0)

    def test_graceful_when_canonical_table_missing(self):
        """If product_recipe_components doesn't exist, return legacy rows."""
        conn = _conn()  # no schema
        conn.executescript("""
            CREATE TABLE productos (id INTEGER PRIMARY KEY, nombre TEXT);
            CREATE TABLE receta_componentes (
                id INTEGER PRIMARY KEY, receta_id INTEGER,
                producto_id INTEGER, rendimiento_porcentaje REAL DEFAULT 0,
                merma_porcentaje REAL DEFAULT 0, orden INTEGER DEFAULT 0
            );
        """)
        conn.execute("INSERT INTO productos (id, nombre) VALUES (1,'P')")
        conn.execute(
            "INSERT INTO receta_componentes (id, receta_id, producto_id, rendimiento_porcentaje) "
            "VALUES (1, 3, 1, 70.0)"
        )
        eng = _make_engine(conn)
        rows = eng._get_receta_componentes(conn, 3)
        assert len(rows) == 1
        assert rows[0]["rendimiento_porcentaje"] == pytest.approx(70.0)


# ═══════════════════════════════════════════════════════════════════════════════
# B. ProductionEngine._get_expected_yield_pct()
# ═══════════════════════════════════════════════════════════════════════════════

class TestGetExpectedYieldPct:

    def _engine_and_conn(self):
        conn = _conn(_minimal_schema())
        eng  = _make_engine(conn)
        return eng, conn

    def test_reads_from_product_recipes(self):
        eng, conn = self._engine_and_conn()
        conn.execute(
            "INSERT INTO product_recipes (id, rendimiento_esperado_pct, merma_esperada_pct) "
            "VALUES (1, 80.0, 5.0)"
        )
        r, m = eng._get_expected_yield_pct(conn, 1)
        assert r == pytest.approx(80.0)
        assert m == pytest.approx(5.0)

    def test_returns_zeros_when_no_row(self):
        eng, conn = self._engine_and_conn()
        r, m = eng._get_expected_yield_pct(conn, 99)
        assert r == 0.0
        assert m == 0.0

    def test_falls_back_to_legacy_recetas(self):
        """When product_recipes has no row, use legacy recetas."""
        eng, conn = self._engine_and_conn()
        conn.execute(
            "INSERT INTO recetas (id, rendimiento_esperado_pct, merma_esperada_pct) "
            "VALUES (5, 75.0, 8.0)"
        )
        r, m = eng._get_expected_yield_pct(conn, 5)
        assert r == pytest.approx(75.0)
        assert m == pytest.approx(8.0)

    def test_canonical_takes_priority_over_legacy(self):
        eng, conn = self._engine_and_conn()
        conn.execute(
            "INSERT INTO product_recipes (id, rendimiento_esperado_pct, merma_esperada_pct) "
            "VALUES (2, 90.0, 1.0)"
        )
        conn.execute(
            "INSERT INTO recetas (id, rendimiento_esperado_pct, merma_esperada_pct) "
            "VALUES (2, 50.0, 20.0)"
        )
        r, m = eng._get_expected_yield_pct(conn, 2)
        assert r == pytest.approx(90.0)
        assert m == pytest.approx(1.0)

    def test_handles_null_values(self):
        eng, conn = self._engine_and_conn()
        conn.execute(
            "INSERT INTO product_recipes (id, rendimiento_esperado_pct, merma_esperada_pct) "
            "VALUES (3, NULL, NULL)"
        )
        r, m = eng._get_expected_yield_pct(conn, 3)
        assert r == 0.0
        assert m == 0.0

    def test_graceful_when_table_missing(self):
        """Graceful degradation when neither table exists."""
        conn = sqlite3.connect(":memory:")
        eng = _make_engine(conn)
        r, m = eng._get_expected_yield_pct(conn, 1)
        assert r == 0.0
        assert m == 0.0


# ═══════════════════════════════════════════════════════════════════════════════
# C. ProductionApplicationService.ejecutar_produccion() dispatcher
# ═══════════════════════════════════════════════════════════════════════════════

class TestProductionApplicationServiceDispatcher:

    def _make_service(self, recipe_engine=None):
        from core.services.production_application_service import ProductionApplicationService
        mock_recipe = recipe_engine or MagicMock()
        return ProductionApplicationService(
            recipe_engine    = mock_recipe,
            production_uc    = None,
            production_engine= None,
        ), mock_recipe

    def test_ejecutar_produccion_delegates_to_recipe_engine(self):
        svc, mock_recipe = self._make_service()
        mock_recipe.ejecutar_produccion.return_value = SimpleNamespace(produccion_id=42)

        result = svc.ejecutar_produccion(
            receta_id    = 1,
            cantidad_base= 10.0,
            usuario      = "test",
            sucursal_id  = 1,
        )

        mock_recipe.ejecutar_produccion.assert_called_once_with(
            receta_id         = 1,
            cantidad_base     = 10.0,
            usuario           = "test",
            sucursal_id       = 1,
            notas             = "",
            operation_id      = None,
            mediciones_reales = None,
        )
        assert result.produccion_id == 42

    def test_ejecutar_produccion_passes_notas(self):
        svc, mock_recipe = self._make_service()
        mock_recipe.ejecutar_produccion.return_value = SimpleNamespace()
        svc.ejecutar_produccion(
            receta_id=2, cantidad_base=5.0, usuario="u", notas="Test note"
        )
        _, kwargs = mock_recipe.ejecutar_produccion.call_args
        assert kwargs["notas"] == "Test note"

    def test_ejecutar_produccion_passes_operation_id(self):
        svc, mock_recipe = self._make_service()
        mock_recipe.ejecutar_produccion.return_value = SimpleNamespace()
        svc.ejecutar_produccion(
            receta_id=1, cantidad_base=1.0, usuario="u", operation_id="op-123"
        )
        _, kwargs = mock_recipe.ejecutar_produccion.call_args
        assert kwargs["operation_id"] == "op-123"

    def test_ejecutar_produccion_passes_mediciones_reales(self):
        svc, mock_recipe = self._make_service()
        mock_recipe.ejecutar_produccion.return_value = SimpleNamespace()
        mediciones = {1: 12.5, 2: 8.0}
        svc.ejecutar_produccion(
            receta_id=1, cantidad_base=20.0, usuario="u",
            mediciones_reales=mediciones
        )
        _, kwargs = mock_recipe.ejecutar_produccion.call_args
        assert kwargs["mediciones_reales"] == mediciones

    def test_ejecutar_produccion_propagates_exception(self):
        from core.services.recipe_engine import RecipeEngineError
        svc, mock_recipe = self._make_service()
        mock_recipe.ejecutar_produccion.side_effect = RecipeEngineError("fallo")
        with pytest.raises(RecipeEngineError):
            svc.ejecutar_produccion(receta_id=1, cantidad_base=1.0, usuario="u")

    def test_ejecutar_receta_still_works_as_alias(self):
        """ejecutar_receta() must still delegate to RecipeEngine (backward compat)."""
        svc, mock_recipe = self._make_service()
        mock_recipe.ejecutar_produccion.return_value = SimpleNamespace(produccion_id=7)
        result = svc.ejecutar_receta(receta_id=3, cantidad_base=2.0, usuario="u")
        mock_recipe.ejecutar_produccion.assert_called_once()
        assert result.produccion_id == 7

    def test_preview_receta_delegates_to_recipe_engine(self):
        svc, mock_recipe = self._make_service()
        mock_recipe.preview_produccion.return_value = [{"delta": -10.0}]
        movs = svc.preview_receta(receta_id=5, cantidad_base=10.0)
        mock_recipe.preview_produccion.assert_called_once_with(5, 10.0)
        assert len(movs) == 1

    def test_from_container_classmethod(self):
        """from_container() builds service from AppContainer attributes."""
        from core.services.production_application_service import ProductionApplicationService
        mock_container = SimpleNamespace(
            recipe_engine     = MagicMock(),
            uc_produccion     = MagicMock(),
            production_engine = MagicMock(),
        )
        svc = ProductionApplicationService.from_container(mock_container)
        assert svc._recipe is mock_container.recipe_engine
        assert svc._uc     is mock_container.uc_produccion
        assert svc._engine is mock_container.production_engine


# ═══════════════════════════════════════════════════════════════════════════════
# D. Integration: _get_receta_componentes feeds load_outputs_from_receta
# ═══════════════════════════════════════════════════════════════════════════════

class TestLoadOutputsFromRecetaUsesCanonical:
    """
    Verify that load_outputs_from_receta() correctly calls add_output() using
    data normalised by _get_receta_componentes() (canonical column names).
    """

    def test_loads_outputs_from_canonical_components(self):
        conn = _conn(_minimal_schema())
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS production_batches (
                id TEXT PRIMARY KEY, folio TEXT, product_source_id INTEGER,
                source_weight REAL, processed_weight REAL DEFAULT 0,
                waste_weight REAL DEFAULT 0, source_cost_total REAL DEFAULT 0,
                branch_id INTEGER DEFAULT 1, receta_id INTEGER,
                estado TEXT DEFAULT 'abierto', created_by TEXT,
                created_at TEXT, operation_id TEXT, notas TEXT
            );
            CREATE TABLE IF NOT EXISTS production_outputs (
                id TEXT PRIMARY KEY, batch_id TEXT, product_id INTEGER,
                weight REAL, expected_pct REAL DEFAULT 0, expected_weight REAL DEFAULT 0,
                cost_allocated REAL DEFAULT 0, is_waste INTEGER DEFAULT 0,
                UNIQUE(batch_id, product_id)
            );
        """)
        conn.execute(
            "INSERT INTO productos (id, nombre) VALUES (1,'Pechuga'),(2,'Pierna')"
        )
        conn.execute(
            "INSERT INTO product_recipe_components "
            "(id, recipe_id, component_product_id, rendimiento_pct, merma_pct, orden) "
            "VALUES (1,10,1,60.0,0.0,1),(2,10,2,30.0,0.0,2)"
        )

        batch_id = "batch-test-001"
        conn.execute("""
            INSERT INTO production_batches
                (id, folio, product_source_id, source_weight, source_cost_total,
                 branch_id, receta_id, estado, created_by, created_at, operation_id)
            VALUES (?,?,1,100.0,0,1,10,'abierto','test','2025-01-01','op-test')
        """, (batch_id, "PROD-TEST"))

        from core.production.production_engine import ProductionEngine
        eng = ProductionEngine.__new__(ProductionEngine)
        from core.db.connection import wrap
        eng.db = wrap(conn)
        eng.branch_id = 1

        outputs = eng.load_outputs_from_receta(batch_id)
        assert len(outputs) == 2
        weights = {o.product_id: o.weight for o in outputs}
        assert weights[1] == pytest.approx(60.0)  # 100 kg × 60%
        assert weights[2] == pytest.approx(30.0)  # 100 kg × 30%
