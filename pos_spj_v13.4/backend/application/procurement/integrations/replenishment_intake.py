"""Inbound integration: POS / forecast / minimum-stock replenishment needs →
draft purchase requisitions.

The POS never executes purchases; it emits a need. Forecast and minimum-stock do
the same. This handler turns any such need into a DRAFT requisition inside
Compras, idempotently (the source event_id is reused as the requisition's
operation_id, so a re-delivered event never creates a duplicate).
"""

from __future__ import annotations

import logging

from backend.application.procurement.use_cases.requisition_use_cases import (
    CreatePurchaseRequisitionUseCase,
)
from backend.domain.procurement.enums import SourceChannel

logger = logging.getLogger("spj.procurement.replenishment_intake")

#: need event name → source channel recorded on the requisition.
_CHANNEL_BY_EVENT = {
    "STOCK_REPLENISHMENT_REQUIRED": SourceChannel.MINIMUM_STOCK.value,
    "PURCHASE_NEED_DETECTED": SourceChannel.MINIMUM_STOCK.value,
    "PURCHASE_REQUISITION_REQUESTED": SourceChannel.POS_REPLENISHMENT_REQUEST.value,
    "CUSTOMER_ORDER_REQUIRES_PURCHASE": SourceChannel.CUSTOMER_ORDER.value,
    "FORECAST_REPLENISHMENT_SUGGESTED": SourceChannel.FORECAST.value,
}


class ReplenishmentIntakeHandler:
    """Creates a draft requisition from a replenishment-need event."""

    def __init__(self, connection, *, use_case: CreatePurchaseRequisitionUseCase | None = None,
                 default_user_id: str = "system") -> None:
        self._connection = connection
        self._use_case = use_case or CreatePurchaseRequisitionUseCase()
        self._default_user = default_user_id

    def handle(self, payload: dict) -> dict | None:
        event_id = str(payload.get("event_id") or "").strip()
        if not event_id:
            logger.warning("replenishment intake: evento sin event_id; se ignora")
            return None
        lines = self._extract_lines(payload)
        if not lines:
            logger.info("replenishment intake: evento %s sin líneas; se ignora", event_id)
            return None
        branch_id = str(payload.get("branch_id") or payload.get("source_branch_id") or "MAIN")
        actor = str(payload.get("requested_by_user_id") or self._default_user)
        channel = _CHANNEL_BY_EVENT.get(
            str(payload.get("event_name") or ""), SourceChannel.MINIMUM_STOCK.value)
        result = self._use_case.execute(
            self._connection, actor_user_id=actor, operation_id=event_id,
            branch_id=branch_id, purchase_type=str(payload.get("purchase_type") or "INVENTORY"),
            lines=lines, priority=str(payload.get("priority") or "NORMAL"),
            business_reason=str(payload.get("reason") or "Reabasto automático"),
            source_channel=channel,
            source_reference_id=payload.get("document_id") or payload.get("source_reference_id"))
        return {"success": result.success, "requisition_id": result.entity_id,
                "message": result.message}

    @staticmethod
    def _extract_lines(payload: dict) -> list[dict]:
        raw_lines = payload.get("lines")
        if isinstance(raw_lines, list) and raw_lines:
            return [{"product_id": ln.get("product_id"),
                     "quantity": str(ln.get("quantity") or ln.get("suggested_quantity") or "0")}
                    for ln in raw_lines if ln.get("product_id")]
        product_id = payload.get("product_id")
        quantity = payload.get("quantity") or payload.get("suggested_quantity")
        if product_id and quantity is not None:
            return [{"product_id": product_id, "quantity": str(quantity)}]
        return []
