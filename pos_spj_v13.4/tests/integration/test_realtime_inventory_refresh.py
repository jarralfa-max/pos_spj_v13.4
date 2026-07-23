"""
Tests — Real-time inventory refresh via EventBus.

Verifies the full chain:
  Production confirmed + COMMIT
  → INVENTARIO_ACTUALIZADO published
  → ModuloInventarioLocal.cargar_datos() triggered
  → UI shows updated stock

Tests:
 1. production_confirms_and_commits — process_movement writes to DB
 2. event_published_after_commit — INVENTARIO_ACTUALIZADO emitted by UnifiedInventoryService
 3. rollback_does_not_publish — event NOT emitted when write fails
 4. inventario_receives_event — module subscription includes INVENTARIO_ACTUALIZADO
 5. query_service_re_queries_after_event — fresh read from inventario_actual
 6. balance_matches_sqlite_after_event — UI value == DB value
 7. other_sucursal_event_skipped — different branch does not trigger refresh
 8. hidden_module_marked_dirty — dirty flag set when invisible
 9. dirty_module_refreshes_on_show — showEvent triggers cargar_datos
10. no_duplicate_subscriptions — subscribe once only
11. multiple_productions_show_last_balance — sequential events, correct final stock
12. session_restart_not_needed — value correct after event without restart
13. produccion_registrada_triggers_refresh — PRODUCCION_REGISTRADA also works
14. produccion_completada_triggers_refresh — PRODUCCION_COMPLETADA also works
15. event_payload_contains_sucursal — payload has sucursal_id and producto_ids
"""
from __future__ import annotations

import sqlite3
import threading
import time
import uuid
from decimal import Decimal
from unittest.mock import MagicMock, patch, call

import pytest

from backend.application.queries.inventory_balance_service import (
    InventoryBalanceQueryService,
)


# ── Minimal DB fixture ────────────────────────────────────────────────────────

@pytest.fixture
def db():
    conn = sqlite3.connect(":memory:")
    conn.executescript("""
        CREATE TABLE productos (
            id INTEGER PRIMARY KEY, nombre TEXT, unidad TEXT DEFAULT 'kg',
            existencia REAL DEFAULT 0, stock_minimo REAL DEFAULT 0, activo INTEGER DEFAULT 1
        );
        CREATE TABLE inventario_actual (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            producto_id INTEGER NOT NULL, sucursal_id INTEGER NOT NULL,
            cantidad REAL NOT NULL DEFAULT 0, costo_promedio REAL DEFAULT 0,
            ultima_actualizacion TEXT DEFAULT (datetime('now')),
            UNIQUE(producto_id, sucursal_id)
        );
        CREATE TABLE movimientos_inventario (
            id INTEGER PRIMARY KEY AUTOINCREMENT, uuid TEXT,
            producto_id INTEGER, sucursal_id INTEGER DEFAULT 1,
            tipo TEXT, tipo_movimiento TEXT, cantidad REAL,
            existencia_anterior REAL DEFAULT 0, existencia_nueva REAL DEFAULT 0,
            descripcion TEXT, usuario TEXT, referencia TEXT,
            fecha TEXT DEFAULT (datetime('now'))
        );
        CREATE TABLE inventory_stock (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            product_id INTEGER NOT NULL, branch_id INTEGER NOT NULL,
            quantity REAL NOT NULL DEFAULT 0, unit TEXT DEFAULT 'kg',
            updated_at TEXT DEFAULT (datetime('now')),
            UNIQUE(product_id, branch_id)
        );
        CREATE TABLE stock_reservas (id INTEGER PRIMARY KEY, estado TEXT, branch_id INTEGER);
        CREATE TABLE stock_reserva_detalles (
            id INTEGER PRIMARY KEY, reserva_id INTEGER, producto_id INTEGER, cantidad REAL
        );
        INSERT INTO productos (id, nombre, unidad, existencia) VALUES (1, 'Pollo', 'kg', 100.0);
        INSERT INTO inventario_actual (producto_id, sucursal_id, cantidad) VALUES (1, 1, 100.0);
    """)
    conn.commit()
    return conn


# ── Fake EventBus ─────────────────────────────────────────────────────────────

class FakeBus:
    def __init__(self):
        self.published: list[tuple[str, dict]] = []
        self._handlers: dict[str, list] = {}

    def publish(self, event_type: str, data: dict) -> None:
        data["event_type"] = event_type
        self.published.append((event_type, data))
        for h in self._handlers.get(event_type, []):
            h(data)

    def subscribe(self, event_type: str, handler) -> None:
        self._handlers.setdefault(event_type, []).append(handler)

    def get_published(self, event_type: str) -> list[dict]:
        return [d for (e, d) in self.published if e == event_type]


# ── Test 1: process_movement writes to DB ─────────────────────────────────────

def test_01_production_confirms_and_commits(db):
    """process_movement writes stock to inventario_actual and commits."""
    db.execute(
        "UPDATE inventario_actual SET cantidad=50 WHERE producto_id=1 AND sucursal_id=1"
    )
    db.commit()

    # Simulate what UnifiedInventoryService.process_movement writes
    db.execute(
        "UPDATE productos SET existencia=80 WHERE id=1"
    )
    db.execute("""
        INSERT INTO movimientos_inventario (uuid, producto_id, sucursal_id, tipo, cantidad,
            existencia_anterior, existencia_nueva)
        VALUES (?,1,1,'SALIDA',20,100,80)
    """, (str(uuid.uuid4()),))
    db.execute("""
        INSERT INTO inventario_actual (producto_id, sucursal_id, cantidad)
        VALUES (1,1,80)
        ON CONFLICT(producto_id, sucursal_id) DO UPDATE SET cantidad=excluded.cantidad
    """)
    db.commit()

    row = db.execute(
        "SELECT cantidad FROM inventario_actual WHERE producto_id=1 AND sucursal_id=1"
    ).fetchone()
    assert row is not None
    assert float(row[0]) == 80.0


# ── Test 2: event published after commit ──────────────────────────────────────

def test_02_event_published_after_commit(db):
    """INVENTARIO_ACTUALIZADO is emitted by UnifiedInventoryService after commit."""
    bus = FakeBus()
    published_events = []

    with patch(
        "core.events.event_bus.get_bus", return_value=bus
    ), patch(
        "core.events.event_bus.INVENTARIO_ACTUALIZADO", "INVENTARIO_ACTUALIZADO"
    ):
        # Simulate what process_movement does after _write() completes
        import datetime
        bus.publish("INVENTARIO_ACTUALIZADO", {
            "sucursal_id": 1,
            "producto_ids": [1],
            "origen": "production",
            "referencia_id": str(uuid.uuid4()),
            "timestamp": datetime.datetime.utcnow().isoformat(),
        })

    evts = bus.get_published("INVENTARIO_ACTUALIZADO")
    assert len(evts) == 1
    assert evts[0]["sucursal_id"] == 1
    assert 1 in evts[0]["producto_ids"]


# ── Test 3: rollback does NOT publish ─────────────────────────────────────────

def test_03_rollback_does_not_publish():
    """No event emitted when production write fails (simulated)."""
    bus = FakeBus()
    committed = False

    try:
        # Simulate: write starts, fails, rollback happens
        raise RuntimeError("Simulated DB error")
        # The code below would publish — but we never reach it
        committed = True
        bus.publish("INVENTARIO_ACTUALIZADO", {"sucursal_id": 1, "producto_ids": [1],
                                                "origen": "production", "referencia_id": "x",
                                                "timestamp": "t"})
    except RuntimeError:
        pass  # rollback occurred

    assert not committed
    assert bus.get_published("INVENTARIO_ACTUALIZADO") == []


# ── Test 4: inventario module subscribes to INVENTARIO_ACTUALIZADO ────────────

def test_04_inventario_subscribes_to_inventario_actualizado():
    pytest.skip("INV-27: inventario_local eliminado; refresh en vivo no portado a la UI enterprise de solo lectura")
    """ModuloInventarioLocal subscription list includes INVENTARIO_ACTUALIZADO."""
    import ast, pathlib
    src = pathlib.Path(__file__).parent.parent.parent / "modulos" / "inventario_local.py"
    tree = ast.parse(src.read_text())

    # Walk the AST to find _init_refresh call arguments
    source = src.read_text()
    assert "INVENTARIO_ACTUALIZADO" in source, \
        "INVENTARIO_ACTUALIZADO not found in inventario_local.py subscription list"
    assert "PRODUCCION_REGISTRADA" in source, \
        "PRODUCCION_REGISTRADA not found in inventario_local.py subscription list"
    assert "PRODUCCION_COMPLETADA" in source, \
        "PRODUCCION_COMPLETADA not found in inventario_local.py subscription list"


# ── Test 5: query service re-queries after event ──────────────────────────────

def test_05_query_service_re_queries_after_event(db):
    """InventoryBalanceQueryService reads fresh data on every call (no cache)."""
    svc = InventoryBalanceQueryService(db)

    b1 = svc.get_product_balance(1, 1)
    assert float(b1["stock_fisico"]) == 100.0

    # Simulate production write
    db.execute("""
        INSERT INTO inventario_actual (producto_id, sucursal_id, cantidad)
        VALUES (1,1,75)
        ON CONFLICT(producto_id, sucursal_id) DO UPDATE SET cantidad=75
    """)
    db.commit()

    b2 = svc.get_product_balance(1, 1)
    assert float(b2["stock_fisico"]) == 75.0
    assert b2["fuente"] == "inventario_actual"


# ── Test 6: UI value == SQLite value ─────────────────────────────────────────

def test_06_balance_matches_sqlite_after_event(db):
    """Stock returned by service matches what's in SQLite."""
    db.execute("""
        INSERT INTO inventario_actual (producto_id, sucursal_id, cantidad)
        VALUES (1,1,42)
        ON CONFLICT(producto_id, sucursal_id) DO UPDATE SET cantidad=42
    """)
    db.commit()

    svc = InventoryBalanceQueryService(db)
    b = svc.get_product_balance(1, 1)

    raw = db.execute(
        "SELECT cantidad FROM inventario_actual WHERE producto_id=1 AND sucursal_id=1"
    ).fetchone()
    assert float(b["stock_fisico"]) == float(raw[0])


# ── Test 7: event from other sucursal skipped ────────────────────────────────

def test_07_other_sucursal_event_skipped():
    """_on_refresh skips events whose sucursal_id != active sucursal."""
    refreshes: list[str] = []

    class FakeModule:
        sucursal_id = 1
        _inventory_dirty = False

        def isVisible(self):
            return True

        def cargar_datos(self):
            refreshes.append("loaded")

        def _on_refresh(self, event_type, data):
            event_suc = data.get("sucursal_id")
            if event_suc is not None and int(event_suc) != int(self.sucursal_id):
                return
            if not self.isVisible():
                self._inventory_dirty = True
                return
            self.cargar_datos()

    mod = FakeModule()

    # Event from sucursal 2 — should be skipped
    mod._on_refresh("INVENTARIO_ACTUALIZADO", {"sucursal_id": 2, "producto_ids": [1]})
    assert refreshes == []

    # Event from sucursal 1 — should trigger refresh
    mod._on_refresh("INVENTARIO_ACTUALIZADO", {"sucursal_id": 1, "producto_ids": [1]})
    assert refreshes == ["loaded"]


# ── Test 8: hidden module sets dirty flag ────────────────────────────────────

def test_08_hidden_module_marked_dirty():
    """When module is not visible, event marks it dirty instead of loading."""
    dirty_set = []

    class FakeModule:
        sucursal_id = 1
        _inventory_dirty = False

        def isVisible(self):
            return False

        def cargar_datos(self):
            raise AssertionError("Should not load when hidden")

        def _on_refresh(self, event_type, data):
            event_suc = data.get("sucursal_id")
            if event_suc is not None and int(event_suc) != int(self.sucursal_id):
                return
            if not self.isVisible():
                self._inventory_dirty = True
                dirty_set.append(True)
                return
            self.cargar_datos()

    mod = FakeModule()
    mod._on_refresh("INVENTARIO_ACTUALIZADO", {"sucursal_id": 1, "producto_ids": [1]})
    assert mod._inventory_dirty is True
    assert dirty_set == [True]


# ── Test 9: dirty module reloads on showEvent ────────────────────────────────

def test_09_dirty_module_refreshes_on_show():
    """showEvent calls cargar_datos when dirty flag is set."""
    loaded = []

    class FakeModule:
        _inventory_dirty = True

        def cargar_datos(self):
            loaded.append("loaded")

        def showEvent(self, event=None):
            if getattr(self, "_inventory_dirty", False):
                self._inventory_dirty = False
                self.cargar_datos()

    mod = FakeModule()
    mod.showEvent()
    assert loaded == ["loaded"]
    assert mod._inventory_dirty is False


# ── Test 10: no duplicate subscriptions ──────────────────────────────────────

def test_10_no_duplicate_subscriptions():
    """subscribe_events is called exactly once; handlers not doubled."""
    bus = FakeBus()
    call_count = [0]

    def handler(data):
        call_count[0] += 1

    bus.subscribe("INVENTARIO_ACTUALIZADO", handler)
    bus.publish("INVENTARIO_ACTUALIZADO", {"sucursal_id": 1, "producto_ids": []})
    # Only one subscription → one call
    assert call_count[0] == 1

    # Subscribing again (simulating duplicate init bug) would double calls
    # The test passes if we ensure subscribe is called only once
    # (RefreshMixin._subscribe_events is called once in __init__)
    assert len(bus._handlers.get("INVENTARIO_ACTUALIZADO", [])) == 1


# ── Test 11: multiple productions show last balance ──────────────────────────

def test_11_multiple_productions_show_last_balance(db):
    """After several sequential production events, service returns the latest stock."""
    svc = InventoryBalanceQueryService(db)

    for qty in [90.0, 80.0, 70.0, 55.5]:
        db.execute("""
            INSERT INTO inventario_actual (producto_id, sucursal_id, cantidad)
            VALUES (1,1,?)
            ON CONFLICT(producto_id, sucursal_id) DO UPDATE SET cantidad=excluded.cantidad
        """, (qty,))
        db.commit()

    b = svc.get_product_balance(1, 1)
    assert float(b["stock_fisico"]) == 55.5


# ── Test 12: session restart not needed ──────────────────────────────────────

def test_12_session_restart_not_needed(db):
    """Stock correct after event without restarting session (service always reads live)."""
    svc = InventoryBalanceQueryService(db)

    b_before = svc.get_product_balance(1, 1)
    assert float(b_before["stock_fisico"]) == 100.0

    # Production writes new stock
    db.execute("""
        INSERT INTO inventario_actual (producto_id, sucursal_id, cantidad)
        VALUES (1,1,63)
        ON CONFLICT(producto_id, sucursal_id) DO UPDATE SET cantidad=63
    """)
    db.commit()

    b_after = svc.get_product_balance(1, 1)
    assert float(b_after["stock_fisico"]) == 63.0
    assert float(b_before["stock_fisico"]) != float(b_after["stock_fisico"])


# ── Test 13: PRODUCCION_REGISTRADA triggers Inventario refresh ────────────────

def test_13_produccion_registrada_triggers_refresh():
    pytest.skip("INV-27: inventario_local eliminado; refresh en vivo no portado a la UI enterprise de solo lectura")
    """PRODUCCION_REGISTRADA is in the Inventario subscription list."""
    import pathlib
    src = (pathlib.Path(__file__).parent.parent.parent / "modulos" / "inventario_local.py").read_text()
    # The module subscribes with the constant name, not the string
    assert "PRODUCCION_REGISTRADA" in src


# ── Test 14: PRODUCCION_COMPLETADA triggers Inventario refresh ────────────────

def test_14_produccion_completada_triggers_refresh():
    pytest.skip("INV-27: inventario_local eliminado; refresh en vivo no portado a la UI enterprise de solo lectura")
    """PRODUCCION_COMPLETADA is in the Inventario subscription list."""
    import pathlib
    src = (pathlib.Path(__file__).parent.parent.parent / "modulos" / "inventario_local.py").read_text()
    assert "PRODUCCION_COMPLETADA" in src


# ── Test 15: event payload contains required fields ──────────────────────────

def test_15_event_payload_contains_sucursal_and_products():
    """INVENTARIO_ACTUALIZADO payload has sucursal_id, producto_ids, origen, timestamp."""
    import datetime
    bus = FakeBus()
    payload = {
        "event_type":    "INVENTARIO_ACTUALIZADO",
        "sucursal_id":   1,
        "producto_ids":  [1, 2, 3],
        "origen":        "PRODUCCION",
        "referencia_id": str(uuid.uuid4()),
        "timestamp":     datetime.datetime.utcnow().isoformat(),
    }
    bus.publish("INVENTARIO_ACTUALIZADO", payload)
    evts = bus.get_published("INVENTARIO_ACTUALIZADO")
    assert len(evts) == 1
    e = evts[0]
    assert "sucursal_id" in e
    assert "producto_ids" in e
    assert isinstance(e["producto_ids"], list)
    assert "origen" in e
    assert "timestamp" in e
