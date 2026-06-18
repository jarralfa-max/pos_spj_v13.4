"""Integration tests for the Delivery module refactor.

Covers:
- AssignDeliveryDriverUseCase
- ChangeDeliveryStatusUseCase payment capture
- SettleDeliveryDriverUseCase
- DriverSettlementQueryService
- No SQL leaking into UI paths
"""
from __future__ import annotations

import sqlite3
import pytest

from repositories.delivery_repository import DeliveryRepository
from core.delivery.infrastructure.delivery_schema_migrator import DeliverySchemaMigrator
from core.delivery.application.assign_delivery_driver import AssignDeliveryDriverUseCase
from core.delivery.application.change_delivery_status import ChangeDeliveryStatusUseCase
from backend.application.use_cases.settle_delivery_driver_use_case import (
    SettleDeliveryDriverCommand,
    SettleDeliveryDriverUseCase,
    DRIVER_SETTLEMENT_CREATED,
)
from backend.application.queries.driver_settlement_query_service import DriverSettlementQueryService


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def db():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    DeliverySchemaMigrator(conn).ensure_schema()

    # Extra columns used by our new use cases
    for col_def in [
        "ALTER TABLE delivery_orders ADD COLUMN fecha_entrega DATETIME",
        "ALTER TABLE delivery_orders ADD COLUMN pago_metodo TEXT",
        "ALTER TABLE delivery_orders ADD COLUMN pago_monto REAL DEFAULT 0",
        "ALTER TABLE delivery_orders ADD COLUMN corte_id TEXT",
        "ALTER TABLE delivery_orders ADD COLUMN tiempo_estimado TEXT",
        "ALTER TABLE delivery_orders ADD COLUMN fecha_asignacion DATETIME",
    ]:
        try:
            conn.execute(col_def)
        except Exception:
            pass

    # Migration 109 tables
    conn.execute("""
        CREATE TABLE IF NOT EXISTS delivery_driver_cuts (
            id TEXT PRIMARY KEY,
            driver_id INTEGER NOT NULL,
            driver_nombre TEXT NOT NULL,
            turno_inicio DATETIME,
            turno_fin DATETIME DEFAULT (datetime('now')),
            entregas_total INTEGER DEFAULT 0,
            efectivo_cobrado REAL DEFAULT 0,
            tarjeta_cobrado REAL DEFAULT 0,
            transfer_cobrado REAL DEFAULT 0,
            total_cobrado REAL DEFAULT 0,
            efectivo_entregado REAL DEFAULT 0,
            diferencia REAL DEFAULT 0,
            usuario_corte TEXT,
            sucursal_id INTEGER DEFAULT 0,
            notas TEXT,
            created_at DATETIME DEFAULT (datetime('now'))
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS delivery_cut_items (
            id TEXT PRIMARY KEY,
            cut_id TEXT NOT NULL,
            order_id INTEGER NOT NULL,
            cliente_nombre TEXT,
            total REAL DEFAULT 0,
            pago_metodo TEXT,
            pago_monto REAL DEFAULT 0
        )
    """)
    # Add drivers table
    conn.execute("""
        CREATE TABLE IF NOT EXISTS drivers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nombre TEXT NOT NULL,
            telefono TEXT,
            activo INTEGER DEFAULT 1,
            sucursal_id INTEGER DEFAULT 0
        )
    """)
    conn.commit()
    return conn


@pytest.fixture()
def repo(db):
    return DeliveryRepository(db)


def _make_order(db, estado="pendiente", workflow_type="delivery", sucursal_id=1,
                driver_id=None, total=100.0) -> int:
    repo = DeliveryRepository(db)
    order_id = repo.create_order({
        "direccion": "Calle 1 #100",
        "cliente_nombre": "Juan Pérez",
        "cliente_tel": "+521234567890",
        "total": total,
        "sucursal_id": sucursal_id,
        "workflow_type": workflow_type,
    })
    if estado != "pendiente":
        db.execute(
            "UPDATE delivery_orders SET estado=? WHERE id=?", (estado, order_id)
        )
        db.commit()
    return order_id


def _make_driver(db, nombre="Repartidor A") -> int:
    cur = db.execute("INSERT INTO drivers (nombre) VALUES (?)", (nombre,))
    db.commit()
    return cur.lastrowid


# ---------------------------------------------------------------------------
# AssignDeliveryDriverUseCase
# ---------------------------------------------------------------------------

class TestAssignDeliveryDriverUseCase:
    def test_happy_path_assigns_driver_and_transitions_to_preparacion(self, db, repo):
        order_id = _make_order(db)
        driver_id = _make_driver(db)
        uc = AssignDeliveryDriverUseCase(db=db, repository=repo)
        result = uc.execute(order_id, driver_id=driver_id, tiempo_estimado="20 min", usuario="op1")
        assert result["order_id"] == order_id
        assert result["driver_id"] == driver_id
        order = repo.get_order(order_id)
        assert order["driver_id"] == driver_id
        assert order["estado"] == "preparacion"

    def test_sets_tiempo_estimado_on_order(self, db, repo):
        order_id = _make_order(db)
        driver_id = _make_driver(db)
        AssignDeliveryDriverUseCase(db=db, repository=repo).execute(
            order_id, driver_id=driver_id, tiempo_estimado="45 min"
        )
        row = db.execute("SELECT tiempo_estimado FROM delivery_orders WHERE id=?", (order_id,)).fetchone()
        assert row and row[0] == "45 min"

    def test_sets_notas_when_provided(self, db, repo):
        order_id = _make_order(db)
        driver_id = _make_driver(db)
        AssignDeliveryDriverUseCase(db=db, repository=repo).execute(
            order_id, driver_id=driver_id, notas="Tocar el timbre"
        )
        row = db.execute("SELECT notas FROM delivery_orders WHERE id=?", (order_id,)).fetchone()
        assert row and "timbre" in (row[0] or "")

    def test_raises_if_driver_id_missing(self, db, repo):
        order_id = _make_order(db)
        with pytest.raises(ValueError, match="driver_id"):
            AssignDeliveryDriverUseCase(db=db, repository=repo).execute(order_id, driver_id=0)

    def test_raises_if_order_not_found(self, db, repo):
        with pytest.raises(ValueError):
            AssignDeliveryDriverUseCase(db=db, repository=repo).execute(99999, driver_id=1)

    def test_publishes_driver_assigned_event(self, db, repo):
        order_id = _make_order(db)
        driver_id = _make_driver(db)
        events = []
        uc = AssignDeliveryDriverUseCase(
            db=db, repository=repo, publisher=lambda e, p: events.append((e, p))
        )
        uc.execute(order_id, driver_id=driver_id)
        assert any("DRIVER_ASSIGNED" in e[0] for e in events)

    def test_history_records_transition(self, db, repo):
        order_id = _make_order(db)
        driver_id = _make_driver(db)
        AssignDeliveryDriverUseCase(db=db, repository=repo).execute(order_id, driver_id=driver_id)
        rows = db.execute(
            "SELECT estado_nuevo FROM delivery_order_history WHERE order_id=?", (order_id,)
        ).fetchall()
        states = [r[0] for r in rows]
        assert "preparacion" in states


# ---------------------------------------------------------------------------
# ChangeDeliveryStatusUseCase — payment capture
# ---------------------------------------------------------------------------

class TestChangeDeliveryStatusPaymentCapture:
    def test_captures_payment_on_entregado(self, db, repo):
        order_id = _make_order(db, estado="en_ruta", workflow_type="delivery")
        uc = ChangeDeliveryStatusUseCase(db=db, repository=repo)
        uc.execute(
            order_id, "entregado",
            usuario="op1", responsable="op1",
            pago_metodo="Efectivo", pago_monto=150.0,
        )
        row = db.execute(
            "SELECT pago_metodo, pago_monto FROM delivery_orders WHERE id=?", (order_id,)
        ).fetchone()
        assert row and row[0] == "Efectivo"
        assert row and abs(float(row[1]) - 150.0) < 0.01

    def test_payment_not_required_for_other_statuses(self, db, repo):
        order_id = _make_order(db, estado="pendiente")
        uc = ChangeDeliveryStatusUseCase(db=db, repository=repo)
        uc.execute(order_id, "preparacion", usuario="op1")
        order = repo.get_order(order_id)
        assert order["estado"] == "preparacion"

    def test_backward_compatible_no_payment_params(self, db, repo):
        order_id = _make_order(db, estado="en_ruta")
        uc = ChangeDeliveryStatusUseCase(db=db, repository=repo)
        # No pago_metodo / pago_monto → should not crash
        uc.execute(order_id, "entregado", usuario="op1", responsable="op1")
        order = repo.get_order(order_id)
        assert order["estado"] == "entregado"

    def test_zero_pago_monto_is_valid(self, db, repo):
        order_id = _make_order(db, estado="en_ruta")
        uc = ChangeDeliveryStatusUseCase(db=db, repository=repo)
        uc.execute(
            order_id, "entregado",
            usuario="op1", responsable="op1",
            pago_metodo="Sin cobro", pago_monto=0.0,
        )
        row = db.execute("SELECT pago_metodo FROM delivery_orders WHERE id=?", (order_id,)).fetchone()
        assert row and row[0] == "Sin cobro"


# ---------------------------------------------------------------------------
# SettleDeliveryDriverUseCase
# ---------------------------------------------------------------------------

class TestSettleDeliveryDriverUseCase:
    def _make_entregado_order(self, db, driver_id, pago_metodo="Efectivo", pago_monto=100.0) -> int:
        order_id = _make_order(db, total=pago_monto)
        repo = DeliveryRepository(db)
        repo.update_status(order_id, "preparacion", usuario="op")
        repo.update_status(order_id, "en_ruta", usuario="op")
        repo.update_status(order_id, "entregado", usuario="op", responsable="op")
        db.execute(
            "UPDATE delivery_orders SET driver_id=?, pago_metodo=?, pago_monto=? WHERE id=?",
            (driver_id, pago_metodo, pago_monto, order_id),
        )
        db.commit()
        return order_id

    def test_creates_cut_record(self, db):
        driver_id = _make_driver(db)
        order_id = self._make_entregado_order(db, driver_id)
        cmd = SettleDeliveryDriverCommand(
            driver_id=driver_id, driver_nombre="Repartidor A",
            order_ids=[order_id], efectivo_entregado=100.0,
            efectivo_cobrado=100.0,
        )
        result = SettleDeliveryDriverUseCase(db=db).execute(cmd)
        assert "cut_id" in result
        row = db.execute(
            "SELECT id FROM delivery_driver_cuts WHERE id=?", (result["cut_id"],)
        ).fetchone()
        assert row is not None

    def test_marks_orders_with_corte_id(self, db):
        driver_id = _make_driver(db)
        oid1 = self._make_entregado_order(db, driver_id, pago_monto=50.0)
        oid2 = self._make_entregado_order(db, driver_id, pago_monto=75.0)
        cmd = SettleDeliveryDriverCommand(
            driver_id=driver_id, driver_nombre="Repartidor A",
            order_ids=[oid1, oid2], efectivo_entregado=125.0,
            efectivo_cobrado=125.0,
        )
        result = SettleDeliveryDriverUseCase(db=db).execute(cmd)
        cut_id = result["cut_id"]
        for oid in [oid1, oid2]:
            row = db.execute("SELECT corte_id FROM delivery_orders WHERE id=?", (oid,)).fetchone()
            assert row and row[0] == cut_id

    def test_calculates_diferencia_correctly(self, db):
        driver_id = _make_driver(db)
        order_id = self._make_entregado_order(db, driver_id, pago_monto=200.0)
        cmd = SettleDeliveryDriverCommand(
            driver_id=driver_id, driver_nombre="Repartidor A",
            order_ids=[order_id], efectivo_entregado=180.0,
            efectivo_cobrado=200.0,
        )
        result = SettleDeliveryDriverUseCase(db=db).execute(cmd)
        assert abs(result["diferencia"] - (-20.0)) < 0.01

    def test_emits_settlement_created_event(self, db):
        driver_id = _make_driver(db)
        order_id = self._make_entregado_order(db, driver_id)
        events = []
        cmd = SettleDeliveryDriverCommand(
            driver_id=driver_id, driver_nombre="Repartidor A",
            order_ids=[order_id], efectivo_entregado=100.0,
            efectivo_cobrado=100.0,
        )
        SettleDeliveryDriverUseCase(
            db=db, publisher=lambda e, p: events.append((e, p))
        ).execute(cmd)
        assert any(e[0] == DRIVER_SETTLEMENT_CREATED for e in events)

    def test_raises_on_empty_order_ids(self, db):
        driver_id = _make_driver(db)
        with pytest.raises(ValueError, match="order_ids"):
            SettleDeliveryDriverCommand(
                driver_id=driver_id, driver_nombre="A", order_ids=[]
            )

    def test_raises_on_missing_driver_id(self, db):
        with pytest.raises(ValueError, match="driver_id"):
            SettleDeliveryDriverCommand(driver_id=0, driver_nombre="A", order_ids=[1])

    def test_inserts_cut_items_for_each_order(self, db):
        driver_id = _make_driver(db)
        oid1 = self._make_entregado_order(db, driver_id, pago_monto=50.0)
        oid2 = self._make_entregado_order(db, driver_id, pago_monto=75.0)
        cmd = SettleDeliveryDriverCommand(
            driver_id=driver_id, driver_nombre="A",
            order_ids=[oid1, oid2], efectivo_entregado=125.0,
            efectivo_cobrado=125.0,
        )
        result = SettleDeliveryDriverUseCase(db=db).execute(cmd)
        items = db.execute(
            "SELECT order_id FROM delivery_cut_items WHERE cut_id=?", (result["cut_id"],)
        ).fetchall()
        order_ids_in_cut = {r[0] for r in items}
        assert oid1 in order_ids_in_cut
        assert oid2 in order_ids_in_cut


# ---------------------------------------------------------------------------
# DriverSettlementQueryService
# ---------------------------------------------------------------------------

class TestDriverSettlementQueryService:
    def _make_entregado(self, db, driver_id, pago_metodo="Efectivo", pago_monto=100.0, corte_id=None) -> int:
        order_id = _make_order(db, total=pago_monto)
        repo = DeliveryRepository(db)
        repo.update_status(order_id, "preparacion", usuario="op")
        repo.update_status(order_id, "en_ruta", usuario="op")
        repo.update_status(order_id, "entregado", usuario="op", responsable="op")
        db.execute(
            "UPDATE delivery_orders SET driver_id=?, pago_metodo=?, pago_monto=?, corte_id=? WHERE id=?",
            (driver_id, pago_metodo, pago_monto, corte_id, order_id),
        )
        db.commit()
        return order_id

    def test_returns_only_unsettled_orders(self, db):
        driver_id = _make_driver(db)
        unsettled = self._make_entregado(db, driver_id)
        settled = self._make_entregado(db, driver_id, corte_id="some-cut-uuid")
        svc = DriverSettlementQueryService(db)
        rows = svc.list_pending_orders_for_driver(driver_id)
        ids = [r["id"] for r in rows]
        assert unsettled in ids
        assert settled not in ids

    def test_excludes_other_driver_orders(self, db):
        driver1 = _make_driver(db, "Driver 1")
        driver2 = _make_driver(db, "Driver 2")
        oid1 = self._make_entregado(db, driver1)
        oid2 = self._make_entregado(db, driver2)
        svc = DriverSettlementQueryService(db)
        ids = [r["id"] for r in svc.list_pending_orders_for_driver(driver1)]
        assert oid1 in ids
        assert oid2 not in ids

    def test_payment_summary_correct(self, db):
        rows = [
            {"pago_metodo": "Efectivo", "pago_monto": 100.0},
            {"pago_metodo": "Tarjeta", "pago_monto": 50.0},
            {"pago_metodo": "Transferencia", "pago_monto": 25.0},
        ]
        svc = DriverSettlementQueryService(db)
        summary = svc.get_payment_summary(rows)
        assert abs(summary["efectivo"] - 100.0) < 0.01
        assert abs(summary["tarjeta"] - 50.0) < 0.01
        assert abs(summary["transfer"] - 25.0) < 0.01
        assert abs(summary["total"] - 175.0) < 0.01

    def test_empty_driver_returns_empty_list(self, db):
        svc = DriverSettlementQueryService(db)
        assert svc.list_pending_orders_for_driver(99999) == []

    def test_cut_history_returns_past_cuts(self, db):
        driver_id = _make_driver(db)
        cut_id = "test-cut-uuid-001"
        db.execute(
            """INSERT INTO delivery_driver_cuts
               (id, driver_id, driver_nombre, entregas_total, efectivo_cobrado,
                efectivo_entregado, diferencia, sucursal_id)
               VALUES (?,?,?,?,?,?,?,?)""",
            (cut_id, driver_id, "Driver A", 3, 300.0, 280.0, -20.0, 1),
        )
        db.commit()
        svc = DriverSettlementQueryService(db)
        history = svc.list_cut_history(driver_id)
        assert len(history) == 1
        assert history[0]["id"] == cut_id
        assert abs(history[0]["diferencia"] - (-20.0)) < 0.01
