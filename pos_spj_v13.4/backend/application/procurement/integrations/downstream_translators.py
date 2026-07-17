"""Translators: procurement events → canonical downstream events.

Each translator is a pure function of (payload) → published downstream events.
They never import the downstream services; they publish canonical events the
inventory / finance / treasury / supplier contexts already subscribe to. The
downstream handlers are idempotent by ``event_id`` (carried through unchanged).
"""

from __future__ import annotations

import logging

from backend.application.procurement.integrations.downstream_events import (
    FORBIDDEN_PAYMENT_SOURCES,
    PAYABLE_CREATED,
    PURCHASE_STOCK_ENTRY_REGISTERED,
    SUPPLIER_PAYMENT_SCHEDULED,
    SUPPLIER_PERFORMANCE_RECORDED,
)
from backend.shared.ids import new_uuid

logger = logging.getLogger("spj.procurement.translators")


def _publish(bus, event_name: str, payload: dict) -> None:
    publish = getattr(bus, "publish", None)
    if publish is None:
        raise RuntimeError("El bus no expone publish()")
    try:
        publish(event_name, payload, async_=False)
    except TypeError:
        publish(event_name, payload)


def _child_event_id(source: dict, suffix: str) -> str:
    """Deterministic-ish child id: keep the source event_id as correlation and
    mint a fresh id so downstream idempotency keys don't collide across fan-out."""
    return f"{source.get('event_id') or new_uuid()}:{suffix}"


class ProcurementDownstreamTranslators:
    """Holds the translator handlers and knows which procurement events feed them."""

    def __init__(self, bus) -> None:
        self._bus = bus

    # inventory ---------------------------------------------------------------
    def on_receipt_completed(self, payload: dict) -> None:
        """A completed receipt (direct or order) enters ACCEPTED qty into stock."""
        lines = payload.get("inventory_lines") or []
        if not lines:
            return
        self._safe_publish(PURCHASE_STOCK_ENTRY_REGISTERED, {
            "event_id": _child_event_id(payload, "inv"),
            "operation_id": payload.get("operation_id"),
            "source_module": "procurement",
            "reason": "PURCHASE_RECEIPT",
            "document_id": payload.get("document_id"),
            "purchase_order_id": payload.get("purchase_order_id"),
            "goods_receipt_id": payload.get("goods_receipt_id"),
            "warehouse_id": payload.get("warehouse_id"),
            "branch_id": payload.get("branch_id"),
            "supplier_id": payload.get("supplier_id"),
            "source_channel": payload.get("source_channel"),
            "document_number": payload.get("document_number"),
            # unit_cost + inventory_unit travel so the Inventory context can compute
            # the weighted-average cost and create lots for weight-tracked lines.
            "lines": [{"product_id": ln.get("product_id"), "quantity": ln.get("quantity"),
                       "unit_cost": ln.get("unit_cost"),
                       "inventory_unit": ln.get("inventory_unit"),
                       "expiration": ln.get("expiration"), "lot": ln.get("lot")}
                      for ln in lines],
        })

    # accounts payable --------------------------------------------------------
    def on_payable_created(self, payload: dict) -> None:
        self._safe_publish(PAYABLE_CREATED, {
            "event_id": _child_event_id(payload, "cxp"),
            "operation_id": payload.get("operation_id"),
            "source_module": "procurement",
            "supplier_id": payload.get("supplier_id"),
            "amount": payload.get("amount"),
            "currency_code": payload.get("currency_code", "MXN"),
            "document_id": payload.get("document_id"),
            "payment_condition": payload.get("payment_condition"),
        })

    # treasury / petty cash ---------------------------------------------------
    def on_payment_requested(self, payload: dict) -> None:
        """Schedule an immediate payment from an authorized source. Defense in
        depth: a POS operative-cash source is rejected here too."""
        source = str(payload.get("payment_source") or "")
        if source in FORBIDDEN_PAYMENT_SOURCES:
            logger.error("procurement: immediate payment from POS cash rejected (doc=%s)",
                         payload.get("document_id"))
            return
        self._safe_publish(SUPPLIER_PAYMENT_SCHEDULED, {
            "event_id": _child_event_id(payload, "pay"),
            "operation_id": payload.get("operation_id"),
            "source_module": "procurement",
            "supplier_id": payload.get("supplier_id"),
            "amount": payload.get("amount"),
            "currency_code": payload.get("currency_code", "MXN"),
            "payment_source": source or None,
            "document_id": payload.get("document_id"),
            "immediate": True,
        })

    # supplier performance ----------------------------------------------------
    def on_receipt_for_performance(self, payload: dict) -> None:
        self._safe_publish(SUPPLIER_PERFORMANCE_RECORDED, {
            "event_id": _child_event_id(payload, "perf"),
            "operation_id": payload.get("operation_id"),
            "source_module": "procurement",
            "supplier_id": payload.get("supplier_id"),
            "document_id": payload.get("document_id"),
            "purchase_order_id": payload.get("purchase_order_id"),
            "signal": "GOODS_RECEIVED",
        })

    # helper ------------------------------------------------------------------
    def _safe_publish(self, event_name: str, payload: dict) -> None:
        try:
            _publish(self._bus, event_name, payload)
        except Exception:
            logger.exception("procurement translator failed for %s", event_name)
