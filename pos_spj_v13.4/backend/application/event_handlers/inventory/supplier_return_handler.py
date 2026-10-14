"""SupplierReturnHandler (Inventory context) — canonical return-to-supplier outflow.

Consumes the CONFIRMED procurement return (PURCHASE_RETURN_CONFIRMED — audit
Compras C12: listening to CREATED would move stock out from a mere draft) and posts a
SUPPLIER_RETURN movement (a DECREASE) to the canonical ledger: stock physically
leaves the warehouse back to the supplier. Returns typically leave from a
non-sellable bucket (a rejected/quarantined lot), so the source status is taken
from the line (default AVAILABLE). Idempotent by the event's operation_id. NOT
live-wired until the INV-27 cutover.

Lote y ubicación (auditoría Compras C12): una recepción de producto con lote deja
su existencia EN ese lote, así que una salida sin ``lot_id`` caía en el bucket sin
lote y se rechazaba como inventario negativo — toda devolución de cárnicos o
perecederos quedaba atorada. Cada línea resuelve su lote por ``lot_id``, luego por
``lot_code`` (lote de Inventario de ese producto) y si no, por el movimiento de la
recepción de origen (``goods_receipt_id``) cuando ahí el producto entró en un solo
lote; de ese mismo movimiento toma la ubicación si la línea no trae una.
"""

from __future__ import annotations

import logging

from backend.application.event_handlers.inventory._ingress import resolve_ingress
from backend.application.inventory.use_cases.post_inventory_movement import (
    PostInventoryMovementUseCase,
)
from backend.domain.inventory.entities.inventory_movement import (
    InventoryMovement,
    InventoryMovementLine,
)
from backend.domain.inventory.enums import InventoryStatus, MovementStatus, MovementType
from backend.infrastructure.db.repositories.inventory.unit_of_work import (
    InventoryUnitOfWork,
)

logger = logging.getLogger("spj.inventory.supplier_return")


class SupplierReturnHandler:
    event_name = "PURCHASE_RETURN_CONFIRMED"

    def __init__(self, connection,
                 use_case: PostInventoryMovementUseCase | None = None) -> None:
        self._conn = connection
        self._uc = use_case or PostInventoryMovementUseCase()

    def handle(self, payload: dict) -> None:
        ingress, reason = resolve_ingress(payload)
        lines = payload.get("lines") or []
        if ingress is None or not lines:
            logger.warning("supplier return: payload inválido (%s); se ignora",
                           reason or "sin líneas")
            return
        user = ingress.actor_user_id
        document_id = str(payload.get("return_id") or ingress.document_id)

        received = self._received_lines(str(payload.get("goods_receipt_id") or ""))
        built = []
        for ln in lines:
            product_id = str(ln.get("product_id") or "")
            if not product_id:
                continue
            status = ln.get("from_status")
            from_status = InventoryStatus(status) if status else InventoryStatus.AVAILABLE
            origin = [r for r in received if r["product_id"] == product_id]
            lot_id = self._resolve_lot(ln, product_id, origin)
            location = (ln.get("from_location_id") or ln.get("location_id")
                        or next((r["to_location_id"] for r in origin
                                 if r.get("to_location_id")), None))
            built.append(InventoryMovementLine.create(
                product_id=product_id, quantity=ln.get("quantity", 0),
                weight=ln.get("weight", 0), unit=ln.get("unit", "PZA"),
                lot_id=lot_id, from_location_id=location,
                from_status=from_status, unit_cost=ln.get("unit_cost"),
                reason_code=ln.get("reason_code")))
        if not built:
            return

        movement = InventoryMovement.create(
            movement_type=MovementType.SUPPLIER_RETURN, branch_id=ingress.branch_id,
            warehouse_id=ingress.warehouse_id, source_module="procurement",
            source_document_type="PURCHASE_RETURN", source_document_id=document_id,
            operation_id=ingress.operation_id, created_by_user_id=user, lines=built)
        result = self._uc.execute(self._conn, movement, actor_user_id=user)
        if not result.success and result.error_code != "PERMISSION_DENIED":
            logger.error("supplier return %s falló: %s", ingress.operation_id,
                         result.message)
            raise RuntimeError(result.message)

    # ── internals ────────────────────────────────────────────────────────────
    def _received_lines(self, goods_receipt_id: str) -> list[dict]:
        """Líneas del movimiento POSTEADO de la recepción de origen."""
        if not goods_receipt_id:
            return []
        with InventoryUnitOfWork(self._conn) as uow:
            movements = uow.ledger.list_for_document("GOODS_RECEIPT", goods_receipt_id)
            posted = [m for m in movements if m["status"] == MovementStatus.POSTED.value]
            return [line for m in posted for line in uow.ledger.get_lines(m["id"])]

    def _resolve_lot(self, ln: dict, product_id: str, origin: list[dict]) -> str | None:
        if ln.get("lot_id"):
            return str(ln["lot_id"])
        code = str(ln.get("lot_code") or "").strip()
        if code:
            with InventoryUnitOfWork(self._conn) as uow:
                lot = uow.lots.get_by_code(product_id, code)
            if lot is not None:
                return lot.id
        lots = {r["lot_id"] for r in origin if r.get("lot_id")}
        if len(lots) == 1:
            return next(iter(lots))
        if len(lots) > 1:
            raise RuntimeError(
                f"La devolución de {product_id} debe indicar de qué lote sale: "
                "la recepción lo registró en varios")
        return None
