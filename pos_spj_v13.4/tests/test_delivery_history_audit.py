import json
import sqlite3

from core.delivery.application.activate_scheduled_order import ActivateScheduledOrderUseCase
from core.delivery.application.cancel_delivery_order import CancelDeliveryOrderUseCase
from core.delivery.application.change_delivery_status import ChangeDeliveryStatusUseCase
from repositories.delivery_repository import DeliveryRepository


def _db():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    repo = DeliveryRepository(conn)
    conn.execute("CREATE TABLE ventas(id INTEGER PRIMARY KEY, estado TEXT, total REAL, workflow_type TEXT)")
    return conn, repo


def test_create_order_writes_auditable_history_and_deprecated_json_compat():
    db, repo = _db()

    order_id = repo.create_order(
        {
            "folio": "DEL-H1",
            "direccion": "Calle Historial 1",
            "cliente_tel": "5512345678",
            "usuario": "tester",
            "source_channel": "whatsapp",
            "venta_id": 10,
        }
    )

    history = db.execute(
        """
        SELECT estado_anterior, estado_nuevo, usuario, reason, metadata_json, created_at
        FROM delivery_order_history WHERE order_id=?
        """,
        (order_id,),
    ).fetchone()
    assert history["estado_anterior"] is None
    assert history["estado_nuevo"] == "pendiente"
    assert history["usuario"] == "tester"
    assert history["reason"] == "order_created"
    assert json.loads(history["metadata_json"]) == {"source_channel": "whatsapp", "venta_id": 10}
    assert history["created_at"] is not None

    raw_json = db.execute("SELECT historial_cambios FROM delivery_orders WHERE id=?", (order_id,)).fetchone()[0]
    legacy_history = json.loads(raw_json)
    assert legacy_history[0]["estado"] == "pendiente"
    assert legacy_history[0]["reason"] == "creación"
    assert legacy_history[0]["created_at"] is not None


def test_change_status_history_has_reason_metadata_and_keeps_legacy_json():
    db, repo = _db()
    order_id = repo.create_order({"direccion": "Calle 2", "usuario": "creator"})

    ChangeDeliveryStatusUseCase(db=db, repository=repo).execute(
        order_id,
        "preparacion",
        usuario="chef",
        observacion="pedido tomado por cocina",
    )

    rows = db.execute(
        """
        SELECT estado_anterior, estado_nuevo, usuario, observacion, reason, metadata_json
        FROM delivery_order_history WHERE order_id=? ORDER BY id
        """,
        (order_id,),
    ).fetchall()
    assert len(rows) == 2
    last = rows[-1]
    assert dict(last) == {
        "estado_anterior": "pendiente",
        "estado_nuevo": "preparacion",
        "usuario": "chef",
        "observacion": "pedido tomado por cocina",
        "reason": "delivery_status_preparacion",
        "metadata_json": '{"responsable": "", "source": "ChangeDeliveryStatusUseCase", "target_status": "preparacion", "venta_id": null}',
    }

    legacy = json.loads(db.execute("SELECT historial_cambios FROM delivery_orders WHERE id=?", (order_id,)).fetchone()[0])
    assert legacy[-1]["estado"] == "preparacion"
    assert legacy[-1]["reason"] == "delivery_status_preparacion"


def test_activate_scheduled_and_cancel_write_status_history_rows():
    db, repo = _db()
    order_id = repo.create_order({"direccion": "Calle 3", "usuario": "creator", "delivery_type": "pickup"})
    repo.update_status(order_id, "programado", usuario="planner", reason="manual_schedule")

    ActivateScheduledOrderUseCase(db=db, repository=repo).execute(order_id, usuario="planner")
    CancelDeliveryOrderUseCase(
        ChangeDeliveryStatusUseCase(db=db, repository=repo)
    ).execute(order_id, usuario="planner", motivo="cliente no llegó")

    rows = db.execute(
        "SELECT estado_anterior, estado_nuevo, reason, observacion FROM delivery_order_history WHERE order_id=? ORDER BY id",
        (order_id,),
    ).fetchall()
    transitions = [(r["estado_anterior"], r["estado_nuevo"], r["reason"], r["observacion"]) for r in rows]
    assert ("programado", "pendiente", "scheduled_order_activated", "activación de pedido programado") in transitions
    assert ("pendiente", "cancelado", "delivery_status_cancelado", "cliente no llegó") in transitions
