"""Canonical procurement events (PUR-1 needs + PUR-3.. lifecycle).

The POS-side "need" events are the ONLY purchase-related signals the POS emits —
it detects needs; Compras decides and executes. All events are published
post-commit with the minimum payload (§70).
"""

from __future__ import annotations

from datetime import datetime, timezone

from backend.shared.ids import new_uuid


class ReplenishmentNeedEvents:
    """Emitted by the POS/inventory/production — needs, never executed purchases."""

    PURCHASE_NEED_DETECTED = "PURCHASE_NEED_DETECTED"
    PURCHASE_REQUISITION_REQUESTED = "PURCHASE_REQUISITION_REQUESTED"
    STOCK_REPLENISHMENT_REQUIRED = "STOCK_REPLENISHMENT_REQUIRED"
    CUSTOMER_ORDER_REQUIRES_PURCHASE = "CUSTOMER_ORDER_REQUIRES_PURCHASE"


class ProcurementEvents:
    # direct purchase
    DIRECT_PURCHASE_DRAFTED = "DIRECT_PURCHASE_DRAFTED"
    DIRECT_PURCHASE_AUTHORIZATION_REQUESTED = "DIRECT_PURCHASE_AUTHORIZATION_REQUESTED"
    DIRECT_PURCHASE_AUTHORIZED = "DIRECT_PURCHASE_AUTHORIZED"
    DIRECT_PURCHASE_CONFIRMED = "DIRECT_PURCHASE_CONFIRMED"
    DIRECT_PURCHASE_RECEIPT_PENDING = "DIRECT_PURCHASE_RECEIPT_PENDING"
    DIRECT_PURCHASE_RECEIVED = "DIRECT_PURCHASE_RECEIVED"
    DIRECT_PURCHASE_REVERSED = "DIRECT_PURCHASE_REVERSED"
    # payments
    PURCHASE_PAYMENT_REQUESTED = "PURCHASE_PAYMENT_REQUESTED"
    PURCHASE_PAYMENT_CONFIRMED = "PURCHASE_PAYMENT_CONFIRMED"
    PURCHASE_PAYABLE_CREATED = "PURCHASE_PAYABLE_CREATED"
    # requisitions
    PURCHASE_REQUISITION_CREATED = "PURCHASE_REQUISITION_CREATED"
    PURCHASE_REQUISITION_SUBMITTED = "PURCHASE_REQUISITION_SUBMITTED"
    PURCHASE_REQUISITION_APPROVED = "PURCHASE_REQUISITION_APPROVED"
    PURCHASE_REQUISITION_REJECTED = "PURCHASE_REQUISITION_REJECTED"
    # rfq / quotes
    RFQ_CREATED = "RFQ_CREATED"
    RFQ_SENT = "RFQ_SENT"
    SUPPLIER_QUOTE_RECEIVED = "SUPPLIER_QUOTE_RECEIVED"
    SUPPLIER_QUOTE_AWARDED = "SUPPLIER_QUOTE_AWARDED"
    # orders
    PURCHASE_ORDER_CREATED = "PURCHASE_ORDER_CREATED"
    PURCHASE_ORDER_APPROVED = "PURCHASE_ORDER_APPROVED"
    PURCHASE_ORDER_SENT = "PURCHASE_ORDER_SENT"
    PURCHASE_ORDER_ACKNOWLEDGED = "PURCHASE_ORDER_ACKNOWLEDGED"
    PURCHASE_ORDER_CHANGED = "PURCHASE_ORDER_CHANGED"
    PURCHASE_ORDER_CANCELLED = "PURCHASE_ORDER_CANCELLED"
    # receipts
    GOODS_RECEIPT_STARTED = "GOODS_RECEIPT_STARTED"
    GOODS_RECEIPT_COMPLETED = "GOODS_RECEIPT_COMPLETED"
    GOODS_RECEIPT_DISCREPANCY = "GOODS_RECEIPT_DISCREPANCY"
    GOODS_RECEIPT_REVERSED = "GOODS_RECEIPT_REVERSED"
    # returns / invoices
    PURCHASE_RETURN_CREATED = "PURCHASE_RETURN_CREATED"
    SUPPLIER_INVOICE_CAPTURED = "SUPPLIER_INVOICE_CAPTURED"
    SUPPLIER_INVOICE_MATCHED = "SUPPLIER_INVOICE_MATCHED"
    SUPPLIER_INVOICE_BLOCKED = "SUPPLIER_INVOICE_BLOCKED"
    # pricing / audit
    PURCHASE_PRICE_VARIANCE_DETECTED = "PURCHASE_PRICE_VARIANCE_DETECTED"
    # umbrella
    PURCHASES_CHANGED = "PURCHASES_CHANGED"


ALL_PROCUREMENT_EVENTS = frozenset(
    v for holder in (ReplenishmentNeedEvents, ProcurementEvents)
    for k, v in vars(holder).items() if not k.startswith("_") and isinstance(v, str)
)


def build_event_payload(event_name: str, *, operation_id: str, document_id: str,
                        document_number: str | None = None,
                        source_channel: str | None = None, supplier_id: str | None = None,
                        branch_id: str | None = None, user_id: str | None = None,
                        authorized_by: str | None = None, terminal_id: str | None = None,
                        source_module: str = "procurement", **extra) -> dict:
    payload = {
        "event_id": new_uuid(),
        "event_name": event_name,
        "operation_id": operation_id,
        "document_id": document_id,
        "document_number": document_number,
        "source_channel": source_channel,
        "supplier_id": supplier_id,
        "branch_id": branch_id,
        "user_id": user_id,
        "authorized_by": authorized_by,
        "terminal_id": terminal_id,
        "timestamp": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "source_module": source_module,
    }
    payload.update(extra)
    return payload
