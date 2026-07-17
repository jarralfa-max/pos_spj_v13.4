"""PUR-13 step 1 — QR reception migrated to the canonical bounded context.

Preserves the legacy behavior (atomic receipt, received qty enters inventory with
its unit cost, pending balance becomes CxP, container advances to received) while
conforming to the new architecture (GoodsReceipt via DirectPurchase, effects as
events, no direct inventory/finance writes, idempotent).
"""

import json
from decimal import Decimal

import pytest

from backend.application.procurement.use_cases.qr_reception_use_cases import (
    CompleteQrReceptionUseCase,
)
from backend.domain.procurement.enums import DocumentStatus, SourceChannel
from backend.infrastructure.db.repositories.procurement.unit_of_work import (
    ProcurementUnitOfWork,
)


@pytest.fixture
def qr_conn(proc_conn):
    """procurement schema + the legacy QR traceability tables."""
    proc_conn.execute(
        "CREATE TABLE trazabilidad_qr (uuid_qr TEXT PRIMARY KEY, estado TEXT,"
        " datos_extra TEXT, fecha_recepcion TEXT, recepcion_id TEXT)")
    proc_conn.execute(
        "CREATE TABLE contenedores_qr (uuid_qr TEXT PRIMARY KEY, estado TEXT,"
        " sucursal_destino TEXT, viaje_actual INTEGER DEFAULT 0, updated_at TEXT)")
    return proc_conn


def _assign(conn, uuid_qr, *, supplier="sup-1", total="500", paid="500"):
    extra = {"proveedor_id": supplier, "condicion_pago": "liquidado",
             "metodo_pago": "efectivo", "monto_pagado": paid, "monto_total": total}
    conn.execute("INSERT INTO trazabilidad_qr (uuid_qr, estado, datos_extra)"
                 " VALUES (?, 'asignado', ?)", (uuid_qr, json.dumps(extra)))
    conn.execute("INSERT INTO contenedores_qr (uuid_qr, estado, viaje_actual)"
                 " VALUES (?, 'en_transito', 0)", (uuid_qr,))
    conn.commit()


def _items():
    return [{"product_id": "p1", "description": "Pollo", "quantity": "10", "unit_cost": "30"},
            {"product_id": "p2", "description": "Caja", "quantity": "5", "unit_cost": "8"}]


def _run(conn, uuid_qr, op="qr-op"):
    return CompleteQrReceptionUseCase().execute(
        conn, actor_user_id="alm", operation_id=op, uuid_qr=uuid_qr, items=_items(),
        branch_id="br-1", warehouse_id="wh-1")


def test_reception_creates_receipt_and_marks_container(qr_conn):
    _assign(qr_conn, "QR-1")
    result = _run(qr_conn, "QR-1")
    assert result.success and result.data["status"] == DocumentStatus.RECEIVED.value
    assert result.data["goods_receipt_id"]

    dp_row = qr_conn.execute(
        "SELECT source_channel, status FROM direct_purchases WHERE id=?",
        (result.entity_id,)).fetchone()
    assert dp_row[0] == SourceChannel.MOBILE_RECEIVING.value
    assert dp_row[1] == DocumentStatus.RECEIVED.value
    # container advanced to received/available
    tqr = qr_conn.execute("SELECT estado, recepcion_id FROM trazabilidad_qr"
                          " WHERE uuid_qr='QR-1'").fetchone()
    assert tqr[0] == "recibido" and tqr[1]
    cont = qr_conn.execute("SELECT estado, viaje_actual FROM contenedores_qr"
                          " WHERE uuid_qr='QR-1'").fetchone()
    assert cont[0] == "disponible" and cont[1] == 1


def test_inventory_event_carries_received_qty_and_cost(qr_conn):
    _assign(qr_conn, "QR-2")
    _run(qr_conn, "QR-2", op="qr-2")
    with ProcurementUnitOfWork(qr_conn) as uow:
        events = uow.outbox.list_pending(50)
    received = next(json.loads(e["payload_json"]) for e in events
                    if e["event_name"] == "DIRECT_PURCHASE_RECEIVED")
    assert received["source_channel"] == SourceChannel.MOBILE_RECEIVING.value
    lines = {l["product_id"]: l for l in received["inventory_lines"]}
    assert lines["p1"]["quantity"] == "10" and lines["p1"]["unit_cost"] == "30"
    assert lines["p2"]["quantity"] == "5" and lines["p2"]["unit_cost"] == "8"


def test_fully_paid_container_raises_no_payable(qr_conn):
    _assign(qr_conn, "QR-3", total="500", paid="500")
    _run(qr_conn, "QR-3", op="qr-3")
    with ProcurementUnitOfWork(qr_conn) as uow:
        names = {e["event_name"] for e in uow.outbox.list_pending(50)}
    assert "PURCHASE_PAYABLE_CREATED" not in names


def test_pending_balance_becomes_payable(qr_conn):
    _assign(qr_conn, "QR-4", total="500", paid="200")
    result = _run(qr_conn, "QR-4", op="qr-4")
    assert result.data["balance"] == "300"
    with ProcurementUnitOfWork(qr_conn) as uow:
        payable = next(json.loads(e["payload_json"]) for e in uow.outbox.list_pending(50)
                       if e["event_name"] == "PURCHASE_PAYABLE_CREATED")
    assert payable["amount"] == "300"


def test_idempotent_by_operation_id(qr_conn):
    _assign(qr_conn, "QR-5")
    a = _run(qr_conn, "QR-5", op="qr-5")
    b = _run(qr_conn, "QR-5", op="qr-5")
    assert a.entity_id == b.entity_id
    assert qr_conn.execute("SELECT COUNT(*) FROM direct_purchases").fetchone()[0] == 1


def test_already_received_container_is_noop(qr_conn):
    _assign(qr_conn, "QR-6")
    _run(qr_conn, "QR-6", op="qr-6a")
    again = _run(qr_conn, "QR-6", op="qr-6b")   # different op, same container
    assert again.success and again.data["status"] == "RECEIVED"
    assert qr_conn.execute("SELECT COUNT(*) FROM direct_purchases").fetchone()[0] == 1


def test_unknown_container_fails(qr_conn):
    result = _run(qr_conn, "QR-NONE", op="qr-none")
    assert not result.success and result.error_code == "QR_NOT_FOUND"


def test_reception_does_not_touch_inventory_tables(qr_conn):
    # No inventory tables exist in this schema; a direct write would raise. The
    # reception must complete purely via events + traceability.
    _assign(qr_conn, "QR-7")
    result = _run(qr_conn, "QR-7", op="qr-7")
    assert result.success
