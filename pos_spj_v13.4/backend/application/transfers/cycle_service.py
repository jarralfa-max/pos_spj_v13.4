"""Ciclo de una transferencia como servicio de aplicación (integración Logística
32cfbf): enviar, aprobar, rechazar, preparar (reservar + surtir + lista),
despachar y recibir. Cada acción es atómica: si un paso falla se revierte lo no
confirmado — la UI no controla transacciones.

Las reglas viven en los casos de uso que orquesta (segregación, saldos,
verificador independiente, alcance por sucursal); aquí sólo se encadenan."""

from __future__ import annotations

import logging
from decimal import Decimal

from backend.application.transfers.commands.transfer_request_commands import (
    ApproveTransferRequestCommand,
    ConfirmTransferPickingCommand,
    ConfirmTransferReceiptCommand,
    DispatchTransferShipmentCommand,
    DispatchTransferShipmentLineCommand,
    ReceiveTransferLineCommand,
    RejectTransferRequestCommand,
    ReserveTransferInventoryCommand,
    StartTransferPickingCommand,
    SubmitTransferRequestCommand,
    TransferPickLineCommand,
)
from backend.domain.transfers.exceptions import TransferError
from backend.shared.ids import new_uuid

logger = logging.getLogger("spj.transfers.cycle")
ZERO = Decimal("0")


class TransferCycleService:
    def __init__(self, connection, *, use_cases: dict, detail_query, pick_lines) -> None:
        self._conn = connection
        self._uc = use_cases
        self._detail = detail_query
        self._pick_lines = pick_lines

    def available(self, action: str) -> bool:
        return action in self._uc

    def detail(self, transfer_id: str) -> dict | None:
        return self._detail(transfer_id)

    def _atomic(self, steps, success: str) -> tuple[bool, str, dict]:
        try:
            for step in steps:
                step()
            return True, success, {}
        except (TransferError, ValueError, PermissionError) as exc:
            self._conn.rollback()
            return False, str(exc), {}
        except Exception as exc:  # noqa: BLE001 - se informa al operador
            self._conn.rollback()
            logger.exception("Transferencias: acción del ciclo fallida")
            return False, str(exc) or "Error inesperado; revise el log.", {}

    def submit(self, transfer_id: str, actor: str):
        return self._atomic([lambda: self._uc["submit"].execute(
            SubmitTransferRequestCommand(transfer_id, actor, new_uuid()))],
            "Solicitud enviada a aprobación.")

    def approve(self, transfer_id: str, actor: str):
        return self._atomic([lambda: self._uc["approve"].execute(
            ApproveTransferRequestCommand(transfer_id, actor, new_uuid()))],
            "Transferencia aprobada.")

    def reject(self, transfer_id: str, actor: str, reason: str):
        return self._atomic([lambda: self._uc["reject"].execute(
            RejectTransferRequestCommand(transfer_id, actor, new_uuid(), reason))],
            "Transferencia rechazada.")

    def prepare(self, transfer_id: str, actor: str):
        """Reservar en Inventario → surtir lo reservado (ubicación y lote que
        eligió Inventario) → lista para despacho. Todo o nada."""
        estado = (self._detail(transfer_id) or {}).get("status", "")

        def surtir():
            lineas = []
            for line_id, partes in self._pick_lines(transfer_id).items():
                total = sum((Decimal(str(q)) for _loc, _lot, q in partes), ZERO)
                if total <= 0:
                    continue
                ubicacion, lote, _q = partes[0]
                lineas.append(TransferPickLineCommand(line_id, total, location_id=ubicacion,
                                                      lot_id=lote))
            if not lineas:
                raise ValueError("No hay nada reservado para surtir.")
            self._uc["confirm_picking"].execute(ConfirmTransferPickingCommand(
                transfer_id, actor, new_uuid(), tuple(lineas)))

        pasos = []
        if estado in ("APPROVED", "RESERVATION_PENDING"):
            pasos.append(lambda: self._uc["reserve"].execute(
                ReserveTransferInventoryCommand(transfer_id, actor, new_uuid())))
        if estado in ("APPROVED", "RESERVATION_PENDING", "RESERVED"):
            pasos.append(lambda: self._uc["start_picking"].execute(
                StartTransferPickingCommand(transfer_id, actor, new_uuid())))
        pasos += [surtir, lambda: self._uc["ready_to_dispatch"].execute(
            transfer_id=transfer_id, user_id=actor, operation_id=new_uuid())]
        return self._atomic(pasos, "Transferencia preparada: lista para despachar.")

    def dispatch(self, transfer_id: str, actor: str, *, verifier_user_id: str, seal: str = "",
                 vehicle: str = "", temperature=None):
        detalle = self._detail(transfer_id) or {}
        lineas = tuple(
            DispatchTransferShipmentLineCommand(
                l["line_id"], Decimal(str(l["picked"])) - Decimal(str(l["dispatched"])))
            for l in detalle.get("lines", ())
            if Decimal(str(l["picked"])) - Decimal(str(l["dispatched"])) > 0)
        if not lineas:
            return False, "No hay nada surtido pendiente de despachar.", {}
        numero = f"{detalle.get('number', 'TRF')}-E{len(detalle.get('shipments', ())) + 1}"
        return self._atomic([lambda: self._uc["dispatch"].execute(DispatchTransferShipmentCommand(
            transfer_id=transfer_id, dispatched_by_user_id=actor,
            verified_by_user_id=verifier_user_id, custody_received_by_user_id=verifier_user_id,
            operation_id=new_uuid(), shipment_number=numero, lines=lineas,
            vehicle_id=vehicle or None, seal_number=seal or None,
            temperature_at_dispatch=temperature))],
            f"Embarque {numero} despachado: la mercancía salió del origen.")

    def receive(self, transfer_id: str, actor: str, shipment_id: str, lines: list[dict]):
        comando = ConfirmTransferReceiptCommand(
            transfer_id=transfer_id, shipment_id=shipment_id, received_by_user_id=actor,
            operation_id=new_uuid(), lines=tuple(ReceiveTransferLineCommand(
                l["line_id"], Decimal(str(l["quantity"])), accepted=bool(l["accepted"]))
                for l in lines))
        return self._atomic([lambda: self._uc["receive"].execute(comando)],
                            "Recepción registrada: la mercancía entró al destino.")
