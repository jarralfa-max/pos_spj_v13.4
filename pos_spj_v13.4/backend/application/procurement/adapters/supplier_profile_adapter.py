"""Adapters implementing Procurement's read-only ports over Suppliers,
Finance and Inventory (``ports.py``).

Mirrors ``product_catalog_adapter.py``'s composition-root pattern: each
adapter is a thin, connection-owning wrapper around an existing query
service in another bounded context, translated into the DTO the port
promises. Procurement use cases/presenters never import the wrapped query
services directly — only these adapters, type-hinted against the Protocols
in ``ports.py``.
"""

from __future__ import annotations

import sqlite3

from backend.application.inventory.queries.receipt_query_service import (
    ReceiptQueryService,
)
from backend.application.procurement.ports import (
    InventoryReceiptStatus,
    SupplierFinancialStanding,
    SupplierProcurementProfile,
)
from backend.application.procurement.queries.supplier_directory_query_service import (
    SupplierDirectoryQueryService,
)
from backend.application.suppliers.queries.supplier_read_services import (
    SupplierDetailQueryService,
    SupplierFinancialSummaryQueryService,
)


class SupplierProfileAdapter:
    """Implements ``SupplierProcurementProfilePort`` by composing
    ``SupplierDetailQueryService`` (header/blocks, owned by Suppliers) with
    ``SupplierDirectoryQueryService`` (purchasing eligibility, owned by
    Procurement's own read of the canonical supplier) so callers get one
    read instead of reimplementing eligibility logic against either table."""

    def __init__(self, connection) -> None:
        self._connection = connection
        self._detail = SupplierDetailQueryService(connection)
        self._directory = SupplierDirectoryQueryService(connection)

    def profile(self, supplier_id: str) -> SupplierProcurementProfile | None:
        try:
            header = self._detail.get_header(supplier_id)
        except sqlite3.OperationalError:
            header = None
        if header is None:
            return None
        try:
            eligibility = self._directory.get_eligibility(supplier_id)
        except sqlite3.OperationalError:
            # ``proveedores`` itself is absent (un-migrated install / narrow
            # fixture) — SupplierDirectoryQueryService only tolerates a
            # missing column, not a missing table. Degrade to the same
            # permissive defaults it uses for the missing-column case, never
            # invent a block.
            eligibility = None
        purchasing_enabled = (
            eligibility.purchasing_enabled if eligibility is not None else True)
        financially_blocked = (
            eligibility.financially_blocked if eligibility is not None else False)
        return SupplierProcurementProfile(
            supplier_id=str(header["id"]),
            legal_name=header["legal_name"],
            trade_name=header.get("trade_name") or None,
            status=header["status"],
            purchasing_enabled=purchasing_enabled,
            financially_blocked=financially_blocked,
            risk_level=header.get("risk_level"),
            rating_grade=header.get("rating_grade"),
            active_blocks=tuple(header.get("active_blocks") or ()),
        )


class SupplierFinanceAdapter:
    """Implements ``ProcurementFinancePort`` by wrapping
    ``SupplierFinancialSummaryQueryService`` (owned by Finance), which
    already tolerates an absent ``payables`` table by returning zeros."""

    def __init__(self, connection) -> None:
        self._summary = SupplierFinancialSummaryQueryService(connection)

    def financial_standing(self, supplier_id: str) -> SupplierFinancialStanding:
        summary = self._summary.summary(supplier_id)
        return SupplierFinancialStanding(
            supplier_id=supplier_id,
            balance=summary["balance"],
            overdue=summary["overdue"],
            open_documents=summary["open_documents"],
        )


class InventoryReceiptStatusAdapter:
    """Implements ``InventoryReceiptStatusPort`` by wrapping
    ``ReceiptQueryService.status_for_document()`` (owned by Inventory)."""

    def __init__(self, connection) -> None:
        self._receipts = ReceiptQueryService(connection)

    def status_for_receipt(self, goods_receipt_id: str) -> InventoryReceiptStatus | None:
        try:
            row = self._receipts.status_for_document(goods_receipt_id)
        except sqlite3.OperationalError:
            return None
        if row is None:
            return None
        return InventoryReceiptStatus(
            goods_receipt_id=goods_receipt_id,
            status=row.get("status"),
            occurred_at=row.get("occurred_at"),
        )
