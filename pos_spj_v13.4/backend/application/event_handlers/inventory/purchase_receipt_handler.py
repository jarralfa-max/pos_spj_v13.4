"""PurchaseReceiptHandler (Inventory context) — canonical procurement→stock inflow.

Consumes a procurement goods-receipt event (GOODS_RECEIPT_COMPLETED /
DIRECT_PURCHASE_RECEIVED) and posts a PURCHASE_RECEIPT movement to the canonical
ledger through PostInventoryMovementUseCase. This is the INV-19 reframing of the
PUR-13 stock-entry handlers onto the born-clean ledger (§34 procurement bridge):

- **Cost reference**: each line's unit_cost is carried on the ledger line, so
  Finance can value the receipt without Inventory computing money.
- **Quality**: a line (or the whole receipt) may land in a non-sellable bucket —
  PENDING_INSPECTION / QUARANTINED — instead of AVAILABLE, so Quality gates it.
- **Lots/traceability**: a lot-coded line creates (idempotently) a canonical
  InventoryLot of PURCHASE origin and links the ledger line to it.

Idempotent by the event's operation_id (a replay short-circuits inside the use
case; lot creation is idempotent by product+code). NOT wired to the live bus:
the legacy stock path still owns stock until the INV-27 cutover, so wiring both
would double-count. Ready to subscribe at cutover.
"""

from __future__ import annotations

import logging

from backend.application.event_handlers.inventory._ingress import resolve_ingress
from backend.application.inventory.use_cases.lot_use_cases import (
    RegisterInventoryLotUseCase,
)
from backend.application.inventory.use_cases.post_inventory_movement import (
    PostInventoryMovementUseCase,
)
from backend.domain.inventory.entities.inventory_movement import (
    InventoryMovement,
    InventoryMovementLine,
)
from backend.domain.inventory.enums import (
    InventoryStatus,
    LotOrigin,
    MovementType,
)

logger = logging.getLogger("spj.inventory.purchase_receipt")

_SOURCE_DOCUMENT_TYPE = "GOODS_RECEIPT"


class PurchaseReceiptHandler:
    event_name = "GOODS_RECEIPT_COMPLETED"

    def __init__(self, connection,
                 use_case: PostInventoryMovementUseCase | None = None,
                 lot_use_case: RegisterInventoryLotUseCase | None = None) -> None:
        self._conn = connection
        self._uc = use_case or PostInventoryMovementUseCase()
        self._lot_uc = lot_use_case or RegisterInventoryLotUseCase()

    def handle(self, payload: dict) -> None:
        ingress, reason = resolve_ingress(payload)
        lines = payload.get("lines") or []
        if ingress is None or not lines:
            logger.warning("purchase receipt: payload inválido (%s); se ignora",
                           reason or "sin líneas")
            return
        user = ingress.actor_user_id
        document_id = str(payload.get("goods_receipt_id") or ingress.document_id)
        quality_hold = bool(payload.get("quality_hold"))

        built = [
            self._build_line(ln, operation_id=ingress.operation_id,
                             branch_id=ingress.branch_id, document_id=document_id,
                             user=user, quality_hold=quality_hold)
            for ln in lines
        ]
        built = [ln for ln in built if ln is not None]
        if not built:
            return

        movement = InventoryMovement.create(
            movement_type=MovementType.PURCHASE_RECEIPT, branch_id=ingress.branch_id,
            warehouse_id=ingress.warehouse_id, source_module="procurement",
            source_document_type=_SOURCE_DOCUMENT_TYPE, source_document_id=document_id,
            operation_id=ingress.operation_id, created_by_user_id=user, lines=built)
        result = self._uc.execute(self._conn, movement, actor_user_id=user)
        if not result.success and result.error_code != "PERMISSION_DENIED":
            logger.error("purchase receipt %s falló: %s", ingress.operation_id,
                         result.message)
            raise RuntimeError(result.message)

    # ── internals ────────────────────────────────────────────────────────────
    def _build_line(self, ln: dict, *, operation_id: str, branch_id: str,
                    document_id: str, user: str, quality_hold: bool):
        product_id = str(ln.get("product_id") or "")
        if not product_id:
            return None
        lot_id = ln.get("lot_id")
        lot_code = ln.get("lot_code")
        if lot_code and not lot_id:
            lot_id = self._ensure_lot(
                product_id=product_id, lot_code=str(lot_code), ln=ln,
                operation_id=operation_id, branch_id=branch_id,
                document_id=document_id, user=user)
        return InventoryMovementLine.create(
            product_id=product_id, quantity=ln.get("quantity", 0),
            weight=ln.get("weight", 0), unit=ln.get("unit", "PZA"), lot_id=lot_id,
            to_location_id=ln.get("to_location_id") or ln.get("location_id"),
            to_status=self._receipt_status(ln, quality_hold),
            unit_cost=ln.get("unit_cost"), reason_code=ln.get("reason_code"))

    def _ensure_lot(self, *, product_id: str, lot_code: str, ln: dict,
                    operation_id: str, branch_id: str, document_id: str,
                    user: str) -> str | None:
        res = self._lot_uc.execute(
            self._conn, product_id=product_id, lot_code=lot_code,
            origin_type=LotOrigin.PURCHASE,
            operation_id=f"{operation_id}:lot:{product_id}:{lot_code}",
            actor_user_id=user, supplier_lot_code=ln.get("supplier_lot_code"),
            expiration_date=ln.get("expiration_date") or ln.get("expiration"),
            origin_document_id=document_id or None, branch_id=branch_id)
        return res.entity_id if res.success else None

    @staticmethod
    def _receipt_status(ln: dict, quality_hold: bool) -> InventoryStatus:
        status = ln.get("to_status")
        if status:
            return InventoryStatus(status)
        if ln.get("quality_hold") or quality_hold:
            return InventoryStatus.PENDING_INSPECTION
        return InventoryStatus.AVAILABLE


class DirectPurchaseReceiptHandler(PurchaseReceiptHandler):
    """Same stock effect for the direct-purchase (QR/express) receipt event."""

    event_name = "DIRECT_PURCHASE_RECEIVED"
