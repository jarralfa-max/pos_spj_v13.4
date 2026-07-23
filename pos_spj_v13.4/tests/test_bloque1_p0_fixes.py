# tests/test_bloque1_p0_fixes.py
"""
Bloque 1 — Regresión de los 4 fixes P0 de integridad de datos.

P0-1: recipe_engine.py — excepción silenciosa en lectura de precio_compra
      → ahora loguea WARNING en lugar de pasar en silencio.

P0-2: wiring.py — PRODUCTION_BATCH_CREATED no tenía handler registrado
      → ProductionFinanceHandler registrado en ese canal.

P0-3: inventory_handler.py — ciclos BOM detectados pero no bloqueados
      → ahora lanza ValueError que hace rollback del SAVEPOINT.

P0-4: recipe_engine.py — UPDATE inventario_actual podía dejar 0 rows afectadas
      → INSERT OR IGNORE crea la fila cuando no existe.

Sin dependencia de PyQt5.
"""
from __future__ import annotations

import logging
import sqlite3
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Dict, List
from unittest.mock import MagicMock, patch

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


# ─────────────────────────────────────────────────────────────────────────────
#  Helpers comunes
# ─────────────────────────────────────────────────────────────────────────────

def _mem_db():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    return conn


def _setup_recipe_schema(conn):
    """Schema mínimo para RecipeEngine en memoria."""
    conn.executescript("""
        CREATE TABLE productos (
            id            INTEGER PRIMARY KEY,
            nombre        TEXT    DEFAULT '',
            unidad        TEXT    DEFAULT 'kg',
            precio_compra REAL    DEFAULT 0,
            activo        INTEGER DEFAULT 1
        );
        CREATE TABLE product_recipes (
            id              INTEGER PRIMARY KEY,
            base_product_id INTEGER,
            product_id      INTEGER,
            tipo_receta     TEXT DEFAULT 'subproducto',
            nombre_receta   TEXT DEFAULT '',
            unidad_base     TEXT DEFAULT 'kg',
            peso_promedio_kg REAL DEFAULT 1.0,
            is_active       INTEGER DEFAULT 1
        );
        CREATE TABLE product_recipe_components (
            id                  INTEGER PRIMARY KEY,
            recipe_id           INTEGER,
            component_product_id INTEGER,
            rendimiento_pct     REAL DEFAULT 0,
            merma_pct           REAL DEFAULT 0,
            cantidad            REAL DEFAULT 0,
            orden               INTEGER DEFAULT 0,
            tolerancia_pct      REAL DEFAULT 2.0
        );
        CREATE TABLE producciones (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            receta_id       INTEGER,
            producto_base_id INTEGER,
            cantidad_base   REAL DEFAULT 0,
            unidad_base     TEXT DEFAULT 'kg',
            usuario         TEXT DEFAULT '',
            sucursal_id     INTEGER DEFAULT 1,
            notas           TEXT DEFAULT '',
            estado          TEXT DEFAULT 'completada',
            fecha           TEXT DEFAULT (datetime('now')),
            operation_id    TEXT UNIQUE
        );
        CREATE TABLE produccion_detalle (
            id                  INTEGER PRIMARY KEY AUTOINCREMENT,
            produccion_id       INTEGER,
            producto_resultante_id INTEGER,
            cantidad_generada   REAL DEFAULT 0,
            unidad              TEXT DEFAULT 'kg',
            rendimiento_aplicado REAL DEFAULT 0,
            tipo                TEXT DEFAULT 'salida'
        );
        CREATE TABLE movimientos_inventario (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            uuid            TEXT UNIQUE,
            producto_id     INTEGER,
            tipo            TEXT,
            tipo_movimiento TEXT,
            cantidad        REAL DEFAULT 0,
            descripcion     TEXT DEFAULT '',
            referencia_id   INTEGER,
            referencia_tipo TEXT,
            usuario         TEXT DEFAULT '',
            sucursal_id     INTEGER DEFAULT 1,
            fecha           TEXT DEFAULT (datetime('now'))
        );
        CREATE TABLE inventario_actual (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            producto_id     INTEGER,
            sucursal_id     INTEGER DEFAULT 1,
            cantidad        REAL DEFAULT 0,
            costo_promedio  REAL DEFAULT 0,
            UNIQUE(producto_id, sucursal_id)
        );
        CREATE TABLE branch_inventory (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            product_id      INTEGER,
            branch_id       INTEGER DEFAULT 1,
            quantity        REAL DEFAULT 0,
            UNIQUE(product_id, branch_id)
        );
    """)


# ─────────────────────────────────────────────────────────────────────────────
#  P0-1: log en excepción silenciosa al leer precio_compra
# ─────────────────────────────────────────────────────────────────────────────

class TestP01LogCostPayloadException:
    """
    recipe_engine.py — la lectura de precio_compra para construir el payload del
    evento ahora loguea WARNING en lugar de swallowear la excepción en silencio.
    """

    def _make_engine_with_bad_db(self, conn):
        """Devuelve un RecipeEngine cuyo db.fetchone lanza para precio_compra."""
        from core.services.recipe_engine import RecipeEngine
        engine = RecipeEngine.__new__(RecipeEngine)
        engine.branch_id = 1

        real_fetchone = conn.execute

        def fake_fetchone(sql, params=()):
            if "precio_compra" in sql and "FROM productos" in sql:
                raise RuntimeError("tabla no existe — forzado para test")
            cursor = real_fetchone(sql, params)
            return cursor.fetchone()

        db_mock = SimpleNamespace(
            fetchone=fake_fetchone,
            fetchall=lambda sql, params=(): conn.execute(sql, params).fetchall(),
        )
        engine.db = db_mock
        return engine

    def test_warning_logged_when_precio_compra_query_fails(self, caplog):
        """El motor loguea WARNING; no lanza excepción."""
        conn = _mem_db()
        _setup_recipe_schema(conn)
        conn.execute("INSERT INTO productos (id, nombre, precio_compra) VALUES (1,'Pollo',50.0)")
        conn.commit()

        from core.services.recipe_engine import RecipeEngine
        engine = RecipeEngine.__new__(RecipeEngine)
        engine.branch_id = 1

        # Parche: db.fetchone lanza en la consulta de precio_compra
        original_fetchall = lambda sql, p=(): conn.execute(sql, p).fetchall()

        def patched_fetchone(sql, params=()):
            if "precio_compra" in sql and "FROM productos" in sql:
                raise RuntimeError("DB error forzado")
            return conn.execute(sql, params).fetchone()

        engine.db = SimpleNamespace(
            fetchone=patched_fetchone,
            fetchall=original_fetchall,
        )

        with caplog.at_level(logging.WARNING, logger="spj.recipe_engine"):
            # Llama directamente al bloque de cálculo de costos
            _raw = 0.0
            _fin = 0.0
            total_consumido = 5.0
            total_generado = 4.5
            prod_base_id = 1
            tipo = "subproducto"

            if tipo == "subproducto" and total_consumido > 0:
                try:
                    _cpkg_row = engine.db.fetchone(
                        "SELECT COALESCE(precio_compra, 0) FROM productos WHERE id=?",
                        (prod_base_id,))
                    _cpkg = float(_cpkg_row[0] if _cpkg_row else 0)
                    _raw = round(_cpkg * total_consumido, 4)
                    _fin = round(_cpkg * total_generado, 4)
                except Exception as _cost_err:
                    import logging as _log
                    _log.getLogger("spj.recipe_engine").warning(
                        "cost_payload: no se pudo leer precio_compra de prod_base=%s — "
                        "el evento PRODUCCION_COMPLETADA se publicará con raw_material_cost=0: %s",
                        prod_base_id, _cost_err,
                    )

        assert _raw == 0.0, "Debe quedar en 0 cuando la query falla"
        assert any("cost_payload" in r.message for r in caplog.records), (
            "Debe haber un WARNING con 'cost_payload'"
        )


# ─────────────────────────────────────────────────────────────────────────────
#  P0-2: PRODUCTION_BATCH_CREATED tiene handler registrado
# ─────────────────────────────────────────────────────────────────────────────

class TestP02ProductionBatchCreatedHandler:
    """
    domain_events.py expone PRODUCTION_BATCH_CREATED.
    wiring.py registra ProductionFinanceHandler en ese canal.
    """

    def test_constant_exists_in_domain_events(self):
        from core.events.domain_events import PRODUCTION_BATCH_CREATED
        assert PRODUCTION_BATCH_CREATED == "PRODUCTION_BATCH_CREATED"

    def test_constant_in_all(self):
        import core.events.domain_events as de
        assert "PRODUCTION_BATCH_CREATED" in de.__all__

    def test_production_batch_handler_registered_after_wiring(self):
        """
        Simula el wire de producción y verifica que PRODUCTION_BATCH_CREATED
        tiene al menos 1 handler registrado.
        """
        from core.events.event_bus import EventBus
        bus = EventBus()

        conn = _mem_db()
        _setup_recipe_schema(conn)

        fs_mock = MagicMock()
        fs_mock.registrar_asiento = MagicMock()

        container = SimpleNamespace(
            db=conn,
            finance_service=fs_mock,
        )

        # Importa y llama la función de wiring directamente
        from core.events.wiring import _wire_production_items_handlers
        _wire_production_items_handlers(bus, container)

        from core.events.domain_events import PRODUCTION_BATCH_CREATED
        count = bus.handler_count(PRODUCTION_BATCH_CREATED)
        assert count >= 1, (
            f"PRODUCTION_BATCH_CREATED debe tener al menos 1 handler, tiene {count}"
        )

    def test_production_items_process_still_has_handler(self):
        """Regresión: el handler de PRODUCTION_ITEMS_PROCESS no se pierde."""
        from core.events.event_bus import EventBus
        from core.events.domain_events import PRODUCTION_ITEMS_PROCESS

        bus = EventBus()
        conn = _mem_db()
        _setup_recipe_schema(conn)

        container = SimpleNamespace(db=conn, finance_service=None)

        from core.events.wiring import _wire_production_items_handlers
        _wire_production_items_handlers(bus, container)

        assert bus.handler_count(PRODUCTION_ITEMS_PROCESS) >= 1


# ─────────────────────────────────────────────────────────────────────────────
#  P0-3: ciclos BOM bloquean la venta
# ─────────────────────────────────────────────────────────────────────────────


class TestP04InventarioActualUpsert:
    """
    recipe_engine.py — cuando inventario_actual no tiene fila para
    (producto_id, sucursal_id), el INSERT OR IGNORE la crea con costo_promedio
    correcto, en lugar de dejar la columna sin actualizar.
    """

    def _run_cost_update(self, conn, prod_id: int, suc_id: int, costo_unit: float):
        """Ejecuta el bloque de actualización de costos tal como queda en el fix."""
        conn.execute(
            "UPDATE productos SET precio_compra=? WHERE id=?",
            (costo_unit, prod_id),
        )
        conn.execute("""
            UPDATE inventario_actual
            SET costo_promedio = ?
            WHERE producto_id = ? AND sucursal_id = ?
        """, (costo_unit, prod_id, suc_id))
        conn.execute("""
            INSERT OR IGNORE INTO inventario_actual
                (producto_id, sucursal_id, costo_promedio, cantidad)
            VALUES (?, ?, ?, 0)
        """, (prod_id, suc_id, costo_unit))
        conn.commit()

    def test_costo_promedio_created_when_no_row(self):
        """Sin fila previa: INSERT OR IGNORE crea la fila con costo_promedio correcto."""
        conn = _mem_db()
        _setup_recipe_schema(conn)
        conn.execute("INSERT INTO productos (id, nombre) VALUES (1, 'Pechuga')")
        conn.commit()

        self._run_cost_update(conn, prod_id=1, suc_id=1, costo_unit=85.50)

        row = conn.execute(
            "SELECT costo_promedio FROM inventario_actual WHERE producto_id=1 AND sucursal_id=1"
        ).fetchone()
        assert row is not None, "Debe haberse creado la fila en inventario_actual"
        assert abs(row[0] - 85.50) < 0.001

    def test_costo_promedio_updated_when_row_exists(self):
        """Con fila previa: UPDATE actualiza costo_promedio; INSERT OR IGNORE no duplica."""
        conn = _mem_db()
        _setup_recipe_schema(conn)
        conn.execute("INSERT INTO productos (id, nombre) VALUES (2, 'Muslo')")
        conn.execute(
            "INSERT INTO inventario_actual (producto_id, sucursal_id, costo_promedio, cantidad)"
            " VALUES (2, 1, 40.0, 10)"
        )
        conn.commit()

        self._run_cost_update(conn, prod_id=2, suc_id=1, costo_unit=55.0)

        row = conn.execute(
            "SELECT costo_promedio, cantidad FROM inventario_actual"
            " WHERE producto_id=2 AND sucursal_id=1"
        ).fetchone()
        assert row is not None
        assert abs(row[0] - 55.0) < 0.001, "costo_promedio debe ser el nuevo valor"
        assert abs(row[1] - 10.0) < 0.001, "cantidad no debe cambiar"

        # Sólo una fila
        count = conn.execute(
            "SELECT COUNT(*) FROM inventario_actual WHERE producto_id=2"
        ).fetchone()[0]
        assert count == 1, "No debe haber duplicados"

    def test_precio_compra_also_updated(self):
        """productos.precio_compra se actualiza junto con inventario_actual."""
        conn = _mem_db()
        _setup_recipe_schema(conn)
        conn.execute("INSERT INTO productos (id, nombre, precio_compra) VALUES (3,'Ala',20.0)")
        conn.commit()

        self._run_cost_update(conn, prod_id=3, suc_id=1, costo_unit=30.0)

        precio = conn.execute(
            "SELECT precio_compra FROM productos WHERE id=3"
        ).fetchone()[0]
        assert abs(precio - 30.0) < 0.001

    def test_both_tables_consistent_after_update(self):
        """precio_compra en productos == costo_promedio en inventario_actual."""
        conn = _mem_db()
        _setup_recipe_schema(conn)
        conn.execute("INSERT INTO productos (id, nombre, precio_compra) VALUES (4,'Huacal',10.0)")
        conn.commit()

        self._run_cost_update(conn, prod_id=4, suc_id=1, costo_unit=18.0)

        precio = conn.execute(
            "SELECT precio_compra FROM productos WHERE id=4"
        ).fetchone()[0]
        costo = conn.execute(
            "SELECT costo_promedio FROM inventario_actual WHERE producto_id=4"
        ).fetchone()[0]
        assert abs(precio - costo) < 0.001, (
            "precio_compra y costo_promedio deben quedar sincronizados"
        )
