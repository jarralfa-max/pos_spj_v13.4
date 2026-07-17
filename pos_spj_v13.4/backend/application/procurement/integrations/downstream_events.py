"""Canonical downstream events procurement emits to other bounded contexts.

Reuses the ERP's canonical names where they exist; adds procurement-specific
signals (supplier performance) that other contexts may subscribe to.
"""

from __future__ import annotations

# Inventory: accepted quantity of a purchase receipt enters stock. Distinct from
# the finance INVENTORY_ADJUSTMENT_REGISTERED (accounting) — this is the physical
# stock entry consumed by the Inventory context, with per-line unit cost.
PURCHASE_STOCK_ENTRY_REGISTERED = "PURCHASE_STOCK_ENTRY_REGISTERED"
# Accounts payable: a matched invoice / credit purchase becomes a payable.
PAYABLE_CREATED = "PAYABLE_CREATED"
# Treasury / petty cash: an immediate payment is scheduled from an authorized
# financial source (NEVER the POS operative cash).
SUPPLIER_PAYMENT_SCHEDULED = "SUPPLIER_PAYMENT_SCHEDULED"
# Suppliers: a completed receipt feeds supplier performance/evaluation.
SUPPLIER_PERFORMANCE_RECORDED = "SUPPLIER_PERFORMANCE_RECORDED"

#: payment sources that must never fund a purchase (POS operative cash).
FORBIDDEN_PAYMENT_SOURCES = frozenset({"POS_CASH", "POS_OPERATIVE_CASH", "CAJA_POS"})
