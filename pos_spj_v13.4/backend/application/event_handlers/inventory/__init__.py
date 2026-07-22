"""Canonical Inventory-context event handlers (born-clean ledger).

These consume other contexts' events and post movements to the canonical ledger
through the inventory use cases. They are a PARALLEL build: none is wired to the
live EventBus yet (the legacy stock path owns stock until the INV-27 cutover, so
wiring both would double-count). They subscribe at cutover.

INV-11 (Sales): SaleIssueHandler, CustomerReturnHandler.
INV-19 (Procurement): PurchaseReceiptHandler / DirectPurchaseReceiptHandler,
SupplierReturnHandler, GoodsReceiptReversedHandler.
"""

from backend.application.event_handlers.inventory.customer_return_handler import (
    CustomerReturnHandler,
)
from backend.application.event_handlers.inventory.goods_receipt_reversed_handler import (
    GoodsReceiptReversedHandler,
)
from backend.application.event_handlers.inventory.purchase_receipt_handler import (
    DirectPurchaseReceiptHandler,
    PurchaseReceiptHandler,
)
from backend.application.event_handlers.inventory.sale_issue_handler import (
    SaleIssueHandler,
)
from backend.application.event_handlers.inventory.slaughter_stub_handler import (
    SlaughterExecutedStubHandler,
)
from backend.application.event_handlers.inventory.supplier_return_handler import (
    SupplierReturnHandler,
)

__all__ = [
    "CustomerReturnHandler",
    "DirectPurchaseReceiptHandler",
    "GoodsReceiptReversedHandler",
    "PurchaseReceiptHandler",
    "SaleIssueHandler",
    "SlaughterExecutedStubHandler",
    "SupplierReturnHandler",
]
