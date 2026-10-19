"""Detalle de una transferencia para las acciones del ciclo (integración
Logística 32cfbf): renglones con nombre del producto y cantidades por etapa, y
lo que falta por recibir de cada embarque. Sólo lectura."""

from __future__ import annotations

from decimal import Decimal

from backend.infrastructure.db.repositories.transfers.transfer_shipment_repository import (
    TransferReceiptRepository,
    TransferShipmentRepository,
)
from backend.infrastructure.db.repositories.transfers.transfer_write_repository import (
    TransferWriteRepository,
)


class TransferDetailQueryService:
    def __init__(self, connection) -> None:
        self._conn = connection

    def _names(self, ids) -> dict[str, str]:
        ids = sorted(set(ids))
        if not ids:
            return {}
        filas = self._conn.execute(
            f"SELECT id, name FROM products WHERE id IN ({','.join('?' for _ in ids)})",
            tuple(ids)).fetchall()
        return {str(r[0]): str(r[1] or "") for r in filas}

    def detail(self, transfer_id: str) -> dict | None:
        transfer = TransferWriteRepository(self._conn).get(transfer_id)
        if transfer is None:
            return None
        nombres = self._names(line.product_id for line in transfer.lines)
        lineas = [{
            "line_id": line.id, "product_id": line.product_id,
            "product_name": nombres.get(line.product_id, ""),
            "requested": line.requested_quantity, "approved": line.approved_quantity,
            "reserved": line.reserved_quantity, "picked": line.picked_quantity,
            "dispatched": line.dispatched_quantity, "received": line.received_quantity,
            "lot_required": line.lot_required,
        } for line in transfer.lines]
        embarques = []
        envios, recibos = TransferShipmentRepository(self._conn), TransferReceiptRepository(self._conn)
        for shipment_id in envios.for_transfer(transfer.id):
            envio = envios.get(shipment_id)
            recibido = recibos.received_totals(shipment_id)
            pendientes = []
            for linea in envio.lines:
                resto = linea.quantity - recibido.get(linea.transfer_line_id,
                                                      (Decimal("0"), Decimal("0")))[0]
                if resto > 0:
                    base = next(l for l in lineas if l["line_id"] == linea.transfer_line_id)
                    pendientes.append({"line_id": linea.transfer_line_id,
                                       "product_name": base["product_name"], "pending": resto})
            embarques.append({"shipment_id": shipment_id, "number": envio.shipment_number,
                              "dispatched_by": envio.dispatched_by_user_id,
                              "pending_lines": pendientes})
        return {"transfer_id": transfer.id, "number": transfer.transfer_number,
                "status": transfer.status.value, "cold_chain": transfer.cold_chain_required,
                "requested_by": transfer.requested_by_user_id, "lines": lineas,
                "shipments": embarques}
