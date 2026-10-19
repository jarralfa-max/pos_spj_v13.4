"""Embarques y recepciones de Transferencias (integración Logística 32cfbf).

Las tablas existían (`transfer_shipments`, `transfer_receipts`,
`transfer_differences`…) pero ningún repositorio las escribía: despachar y
recibir una transferencia no era posible en la aplicación. Estos repositorios
implementan los puertos que ya esperan `DispatchTransferShipmentUseCase` y
`ConfirmTransferReceiptUseCase`.

No confirman por su cuenta salvo `record_operation`, que cierra la transacción
del caso de uso: así el movimiento de Inventario (que se une a la transacción),
el estado de la transferencia y el embarque/recepción se confirman juntos.
"""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

from backend.domain.transfers.entities.transfer_shipment import (
    TransferShipment,
    TransferShipmentLine,
)
from backend.shared.ids import new_uuid


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _product_of(db, transfer_line_id: str) -> str:
    fila = db.execute("SELECT product_id FROM stock_transfer_lines WHERE id=?",
                      (transfer_line_id,)).fetchone()
    return str(fila[0]) if fila else ""


def _record(db, *, transfer_id, operation_id, operation_type, actor_user_id, device_id=None,
            local_sequence=None, sync_status="CONFIRMED") -> None:
    db.execute(
        "INSERT INTO transfer_operations (id, operation_id, transfer_id, operation_type,"
        " actor_user_id, device_id, local_sequence, sync_status, occurred_at)"
        " VALUES (?,?,?,?,?,?,?,?,?)",
        (new_uuid(), operation_id, transfer_id, operation_type, actor_user_id, device_id,
         local_sequence, sync_status, _now()))
    db.commit()


class TransferShipmentRepository:
    def __init__(self, connection) -> None:
        self._db = connection

    def operation_exists(self, operation_id: str) -> bool:
        return self._db.execute("SELECT 1 FROM transfer_operations WHERE operation_id=?",
                                (operation_id,)).fetchone() is not None

    def save(self, shipment: TransferShipment, custody_event) -> None:
        self._db.execute(
            "INSERT INTO transfer_shipments (id, transfer_id, shipment_number,"
            " dispatched_by_user_id, verified_by_user_id, carrier_id, vehicle_id, driver_id,"
            " seal_number, departure_at, expected_arrival_at, temperature_at_dispatch, status,"
            " dispatch_operation_id, created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (shipment.id, shipment.transfer_id, shipment.shipment_number,
             shipment.dispatched_by_user_id, shipment.verified_by_user_id, shipment.carrier_id,
             shipment.vehicle_id, shipment.driver_id, shipment.seal_number, _now(), None,
             None if shipment.temperature_at_dispatch is None
             else str(shipment.temperature_at_dispatch),
             shipment.status, shipment.id, _now()))
        for line in shipment.lines:
            self._db.execute(
                "INSERT INTO transfer_shipment_lines (id, shipment_id, transfer_line_id,"
                " product_id, lot_id, location_id, quantity, weight) VALUES (?,?,?,?,?,?,?,?)",
                (line.id, shipment.id, line.transfer_line_id,
                 _product_of(self._db, line.transfer_line_id), None, None, str(line.quantity),
                 str(line.weight)))
        e = custody_event
        self._db.execute(
            "INSERT INTO transfer_custody_events (id, shipment_id, event_type,"
            " delivered_by_user_id, received_by_user_id, location_id, vehicle_id, seal_number,"
            " temperature, evidence_reference, notes, occurred_at)"
            " VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
            (e.id, e.shipment_id, e.event_type, e.delivered_by_user_id, e.received_by_user_id,
             e.location_id, e.vehicle_id, e.seal_number,
             None if e.temperature is None else str(e.temperature), e.evidence_reference,
             e.notes, e.occurred_at))

    def record_operation(self, *, shipment_id: str, transfer_id: str, operation_id: str,
                         operation_type: str) -> None:
        self._db.execute("UPDATE transfer_shipments SET dispatch_operation_id=? WHERE id=?",
                         (operation_id, shipment_id))
        actor = self._db.execute("SELECT dispatched_by_user_id FROM transfer_shipments WHERE id=?",
                                 (shipment_id,)).fetchone()
        _record(self._db, transfer_id=transfer_id, operation_id=operation_id,
                operation_type=operation_type, actor_user_id=actor[0] if actor else "")

    def get(self, shipment_id: str) -> TransferShipment | None:
        fila = self._db.execute(
            "SELECT id, transfer_id, shipment_number, dispatched_by_user_id, verified_by_user_id,"
            " carrier_id, vehicle_id, driver_id, seal_number, temperature_at_dispatch, status"
            " FROM transfer_shipments WHERE id=?", (shipment_id,)).fetchone()
        if fila is None:
            return None
        lineas = tuple(
            TransferShipmentLine(transfer_line_id=r[1], quantity=Decimal(r[2]),
                                 weight=Decimal(r[3] or "0"), id=r[0])
            for r in self._db.execute(
                "SELECT id, transfer_line_id, quantity, weight FROM transfer_shipment_lines"
                " WHERE shipment_id=?", (shipment_id,)))
        return TransferShipment(
            transfer_id=fila[1], shipment_number=fila[2], dispatched_by_user_id=fila[3],
            verified_by_user_id=fila[4], lines=lineas, carrier_id=fila[5], vehicle_id=fila[6],
            driver_id=fila[7], seal_number=fila[8],
            temperature_at_dispatch=None if fila[9] is None else Decimal(fila[9]),
            status=fila[10], id=fila[0])

    def for_transfer(self, transfer_id: str) -> list[str]:
        return [r[0] for r in self._db.execute(
            "SELECT id FROM transfer_shipments WHERE transfer_id=? ORDER BY created_at",
            (transfer_id,))]


class TransferReceiptRepository:
    def __init__(self, connection) -> None:
        self._db = connection

    def operation_exists(self, operation_id: str) -> bool:
        return self._db.execute("SELECT 1 FROM transfer_operations WHERE operation_id=?",
                                (operation_id,)).fetchone() is not None

    def received_totals(self, shipment_id: str) -> dict[str, tuple[Decimal, Decimal]]:
        totales: dict[str, tuple[Decimal, Decimal]] = {}
        for linea, cantidad, peso in self._db.execute(
                "SELECT l.transfer_line_id, l.observed_quantity, l.observed_weight"
                " FROM transfer_receipt_lines l JOIN transfer_receipts r ON r.id=l.receipt_id"
                " WHERE r.shipment_id=?", (shipment_id,)):
            q, w = totales.get(linea, (Decimal("0"), Decimal("0")))
            totales[linea] = (q + Decimal(cantidad), w + Decimal(peso or "0"))
        return totales

    def save(self, receipt, differences) -> None:
        transfer = self._db.execute("SELECT transfer_id FROM transfer_shipments WHERE id=?",
                                    (receipt.shipment_id,)).fetchone()
        transfer_id = transfer[0] if transfer else ""
        self._db.execute(
            "INSERT INTO transfer_receipts (id, transfer_id, shipment_id, received_by_user_id,"
            " receipt_operation_id, blind, received_at, qr_reference, device_id, local_sequence,"
            " sync_status) VALUES (?,?,?,?,?,0,?,?,?,?,?)",
            (receipt.id, transfer_id, receipt.shipment_id, receipt.received_by_user_id,
             receipt.operation_id, receipt.received_at, receipt.qr_reference, receipt.device_id,
             receipt.local_sequence, receipt.sync_status))
        for line in receipt.lines:
            self._db.execute(
                "INSERT INTO transfer_receipt_lines (id, receipt_id, transfer_line_id, product_id,"
                " lot_id, observed_quantity, observed_weight, observed_pieces,"
                " temperature_at_receipt, expires_on, cold_chain_status, accepted, quality_status)"
                " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (new_uuid(), receipt.id, line.transfer_line_id,
                 _product_of(self._db, line.transfer_line_id), line.lot_id,
                 str(line.observed_quantity), str(line.observed_weight),
                 str(line.observed_pieces),
                 None if line.temperature is None else str(line.temperature), line.expires_on,
                 getattr(line.cold_chain_status, "value", line.cold_chain_status),
                 int(bool(line.accepted)),
                 getattr(line.quality_status, "value", line.quality_status)))
        for d in differences:
            self._db.execute(
                "INSERT INTO transfer_differences (id, transfer_id, transfer_line_id,"
                " difference_type, expected_quantity, actual_quantity, expected_weight,"
                " actual_weight, difference_quantity, difference_weight, severity,"
                " responsible_stage, detected_by_user_id, status, evidence, detected_at)"
                " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (d.id, transfer_id, d.transfer_line_id,
                 getattr(d.difference_type, "value", d.difference_type),
                 str(d.expected_quantity), str(d.actual_quantity), str(d.expected_weight),
                 str(d.actual_weight), str(d.quantity_delta), str(d.weight_delta), d.severity,
                 d.responsible_stage, d.detected_by_user_id or receipt.received_by_user_id,
                 getattr(d.status, "value", d.status), ",".join(d.evidence) or None,
                 d.detected_at))

    def record_operation(self, *, receipt_id: str, transfer_id: str, operation_id: str,
                         operation_type: str, device_id=None, local_sequence=None,
                         sync_status="CONFIRMED") -> None:
        actor = self._db.execute("SELECT received_by_user_id FROM transfer_receipts WHERE id=?",
                                 (receipt_id,)).fetchone()
        _record(self._db, transfer_id=transfer_id, operation_id=operation_id,
                operation_type=operation_type, actor_user_id=actor[0] if actor else "",
                device_id=device_id, local_sequence=local_sequence, sync_status=sync_status)
