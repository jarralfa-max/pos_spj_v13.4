"""ProductionExecutionHandler (Inventory context) — canonical production→stock.

Consumes a production-completed event and posts the two canonical movements that
a manufacturing run implies (§34 production bridge), replacing the legacy
float-based ProductionInventoryHandler:

- **Consumo**: a PRODUCTION_CONSUMPTION movement removes the input materials
  (DECREASE) from their source bucket.
- **Outputs**: a PRODUCTION_OUTPUT movement adds the finished good and its
  co-products / by-products (INCREASE). Each is a distinct classified line;
  lot-coded outputs create (idempotently) a canonical InventoryLot of PRODUCTION
  origin and are linked back to every consumed input lot (PRODUCTION genealogy),
  so a recall walks raw material → finished good.
- **Merma** is implicit and needs no phantom movement: consumed input and
  produced output are different products, so the yield gap simply *is* the loss
  (Finance values it from the cost ledger, INV-16/§30).
- **WIP**: when the run is staged, outputs land in PRODUCTION_HOLD (not sellable)
  until a later release, via each line's to_status / the ``wip`` flag.

Idempotent by the event's operation_id (each movement carries a derived id).
NOT live-wired until the INV-27 cutover.
"""

from __future__ import annotations

import logging

from backend.application.inventory.use_cases.lot_use_cases import (
    RegisterInventoryLotUseCase,
)
from backend.application.inventory.use_cases.post_inventory_movement import (
    PostInventoryMovementUseCase,
)
from backend.application.inventory.use_cases.register_traceability_link import (
    RegisterTraceabilityLinkUseCase,
)
from backend.domain.inventory.entities.inventory_movement import (
    InventoryMovement,
    InventoryMovementLine,
)
from backend.domain.inventory.enums import (
    InventoryStatus,
    LotOrigin,
    MovementType,
    TraceabilityLinkType,
)

logger = logging.getLogger("spj.inventory.production_execution")


class ProductionExecutionHandler:
    event_name = "PRODUCTION_COMPLETED"

    def __init__(self, connection,
                 post_use_case: PostInventoryMovementUseCase | None = None,
                 lot_use_case: RegisterInventoryLotUseCase | None = None,
                 link_use_case: RegisterTraceabilityLinkUseCase | None = None) -> None:
        self._conn = connection
        self._post = post_use_case or PostInventoryMovementUseCase()
        self._lot = lot_use_case or RegisterInventoryLotUseCase()
        self._link = link_use_case or RegisterTraceabilityLinkUseCase()

    def handle(self, payload: dict) -> None:
        operation_id = str(payload.get("operation_id") or payload.get("event_id") or "").strip()
        branch_id = str(payload.get("branch_id") or "").strip()
        warehouse_id = str(payload.get("warehouse_id") or branch_id).strip()
        consumptions = payload.get("consumptions") or []
        outputs = payload.get("outputs") or []
        if not operation_id or not branch_id or (not consumptions and not outputs):
            logger.warning("production: payload incompleto; se ignora")
            return
        user = str(payload.get("user_id") or "system")
        document_id = str(payload.get("production_id") or payload.get("document_id") or "")
        wip = bool(payload.get("wip"))

        input_lot_ids = self._consume(consumptions, operation_id=operation_id,
                                      branch_id=branch_id, warehouse_id=warehouse_id,
                                      document_id=document_id, user=user)
        output_lot_ids = self._produce(outputs, operation_id=operation_id,
                                       branch_id=branch_id, warehouse_id=warehouse_id,
                                       document_id=document_id, user=user, wip=wip)
        self._link_genealogy(input_lot_ids, output_lot_ids, operation_id=operation_id,
                             user=user, document_id=document_id)

    # ── consumption ──────────────────────────────────────────────────────────
    def _consume(self, consumptions, *, operation_id, branch_id, warehouse_id,
                 document_id, user) -> list[str]:
        lot_ids: list[str] = []
        built = []
        for ln in consumptions:
            product_id = str(ln.get("product_id") or "")
            if not product_id:
                continue
            lot_id = ln.get("lot_id")
            if lot_id:
                lot_ids.append(lot_id)
            status = ln.get("from_status")
            built.append(InventoryMovementLine.create(
                product_id=product_id, quantity=ln.get("quantity", 0),
                weight=ln.get("weight", 0), unit=ln.get("unit", "PZA"), lot_id=lot_id,
                from_location_id=ln.get("from_location_id") or ln.get("location_id"),
                from_status=InventoryStatus(status) if status else InventoryStatus.AVAILABLE,
                reason_code=ln.get("reason_code")))
        if built:
            self._post_movement(MovementType.PRODUCTION_CONSUMPTION, built,
                                operation_id=f"{operation_id}:consume", branch_id=branch_id,
                                warehouse_id=warehouse_id, document_id=document_id, user=user)
        return lot_ids

    # ── outputs (finished + co-/by-products) ─────────────────────────────────
    def _produce(self, outputs, *, operation_id, branch_id, warehouse_id,
                 document_id, user, wip) -> list[str]:
        lot_ids: list[str] = []
        built = []
        default_status = (InventoryStatus.PRODUCTION_HOLD if wip
                          else InventoryStatus.AVAILABLE)
        for ln in outputs:
            product_id = str(ln.get("product_id") or "")
            if not product_id:
                continue
            lot_id = ln.get("lot_id")
            lot_code = ln.get("lot_code")
            if lot_code and not lot_id:
                lot_id = self._ensure_lot(product_id=product_id, lot_code=str(lot_code),
                                          ln=ln, operation_id=operation_id,
                                          branch_id=branch_id, document_id=document_id,
                                          user=user)
            if lot_id:
                lot_ids.append(lot_id)
            status = ln.get("to_status")
            built.append(InventoryMovementLine.create(
                product_id=product_id, quantity=ln.get("quantity", 0),
                weight=ln.get("weight", 0), unit=ln.get("unit", "PZA"), lot_id=lot_id,
                to_location_id=ln.get("to_location_id") or ln.get("location_id"),
                to_status=InventoryStatus(status) if status else default_status,
                unit_cost=ln.get("unit_cost"),
                reason_code=ln.get("output_type") or ln.get("reason_code")))
        if built:
            self._post_movement(MovementType.PRODUCTION_OUTPUT, built,
                                operation_id=f"{operation_id}:output", branch_id=branch_id,
                                warehouse_id=warehouse_id, document_id=document_id, user=user)
        return lot_ids

    def _ensure_lot(self, *, product_id, lot_code, ln, operation_id, branch_id,
                    document_id, user) -> str | None:
        res = self._lot.execute(
            self._conn, product_id=product_id, lot_code=lot_code,
            origin_type=LotOrigin.PRODUCTION,
            operation_id=f"{operation_id}:lot:{product_id}:{lot_code}", actor_user_id=user,
            production_lot_code=str(lot_code), origin_document_id=document_id or None,
            production_date=ln.get("production_date"),
            expiration_date=ln.get("expiration_date") or ln.get("expiration"),
            branch_id=branch_id)
        return res.entity_id if res.success else None

    def _link_genealogy(self, input_lot_ids, output_lot_ids, *, operation_id, user,
                        document_id) -> None:
        for parent in input_lot_ids:
            for child in output_lot_ids:
                if parent == child:
                    continue
                self._link.execute(
                    self._conn, parent_lot_id=parent, child_lot_id=child,
                    link_type=TraceabilityLinkType.PRODUCTION,
                    operation_id=f"{operation_id}:link:{parent}:{child}",
                    actor_user_id=user, source_document_type="PRODUCTION_ORDER",
                    source_document_id=document_id)

    def _post_movement(self, movement_type, lines, *, operation_id, branch_id,
                       warehouse_id, document_id, user) -> None:
        movement = InventoryMovement.create(
            movement_type=movement_type, branch_id=branch_id, warehouse_id=warehouse_id,
            source_module="production", source_document_type="PRODUCTION_ORDER",
            source_document_id=document_id, operation_id=operation_id,
            created_by_user_id=user, lines=lines)
        result = self._post.execute(self._conn, movement, actor_user_id=user)
        if not result.success and result.error_code != "PERMISSION_DENIED":
            logger.error("production %s falló: %s", operation_id, result.message)
            raise RuntimeError(result.message)
