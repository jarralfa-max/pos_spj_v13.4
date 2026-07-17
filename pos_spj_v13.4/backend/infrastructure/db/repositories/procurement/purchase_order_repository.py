"""PurchaseOrderRepository — persists the purchase-order aggregate (header + lines)
plus an immutable version-history table. A sensitive change after approval bumps
the version and re-opens approval; the prior snapshot is kept, never overwritten."""

from __future__ import annotations

import json

from backend.domain.procurement.entities import PurchaseOrder, PurchaseOrderLine
from backend.domain.procurement.enums import PurchaseOrderStatus, PurchaseType
from backend.domain.procurement.value_objects import Money
from backend.infrastructure.db.repositories.procurement.base import (
    ProcurementRepositoryBase,
    dec_str,
    now_iso,
    to_decimal,
)
from backend.shared.ids import new_uuid


class PurchaseOrderRepository(ProcurementRepositoryBase):
    def save(self, po: PurchaseOrder) -> None:
        self._execute(
            "INSERT INTO purchase_orders (id, document_number, supplier_id, branch_id,"
            " warehouse_id, currency_code, purchase_type, status, total, version,"
            " created_by_user_id, approved_by_user_id, operation_id, created_at, updated_at)"
            " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)"
            " ON CONFLICT(id) DO UPDATE SET status=excluded.status, total=excluded.total,"
            " version=excluded.version, approved_by_user_id=excluded.approved_by_user_id,"
            " updated_at=excluded.updated_at",
            (po.id, po.document_number, po.supplier_id, po.branch_id, po.warehouse_id,
             po.currency_code, po.purchase_type.value, po.status.value,
             dec_str(po.total().amount), po.version, po.created_by_user_id,
             po.approved_by_user_id, None, po.created_at, po.updated_at))
        self._execute("DELETE FROM purchase_order_lines WHERE purchase_order_id=?", (po.id,))
        for ln in po.lines:
            self._execute(
                "INSERT INTO purchase_order_lines (id, purchase_order_id, product_id,"
                " description, ordered_quantity, unit_price, currency_code,"
                " conversion_factor, received_quantity, accepted_quantity,"
                " rejected_quantity, invoiced_quantity, destination_warehouse_id)"
                " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (ln.id, po.id, ln.product_id, ln.description, dec_str(ln.ordered_quantity),
                 dec_str(ln.unit_price.amount), ln.unit_price.currency_code,
                 dec_str(ln.conversion_factor), dec_str(ln.received_quantity),
                 dec_str(ln.accepted_quantity), dec_str(ln.rejected_quantity),
                 dec_str(ln.invoiced_quantity), ln.destination_warehouse_id))

    def record_version(self, po: PurchaseOrder, *, before: dict | None, reason: str,
                       changed_by_user_id: str | None) -> None:
        self._execute(
            "INSERT INTO purchase_order_versions (id, purchase_order_id, version,"
            " before_json, after_json, reason, changed_by_user_id, created_at)"
            " VALUES (?,?,?,?,?,?,?,?)",
            (new_uuid(), po.id, po.version,
             json.dumps(before) if before is not None else None,
             json.dumps(self.snapshot(po)), reason, changed_by_user_id, now_iso()))

    @staticmethod
    def snapshot(po: PurchaseOrder) -> dict:
        return {"version": po.version, "status": po.status.value,
                "total": str(po.total().amount),
                "lines": [{"product_id": ln.product_id,
                           "ordered_quantity": str(ln.ordered_quantity),
                           "unit_price": str(ln.unit_price.amount)} for ln in po.lines]}

    def set_operation_id(self, purchase_order_id: str, operation_id: str) -> None:
        self._execute("UPDATE purchase_orders SET operation_id=? WHERE id=?",
                      (operation_id, purchase_order_id))

    def get_by_operation(self, operation_id: str) -> PurchaseOrder | None:
        row = self._query_one("SELECT * FROM purchase_orders WHERE operation_id=?",
                              (operation_id,))
        return self._hydrate(row) if row else None

    def get(self, purchase_order_id: str) -> PurchaseOrder | None:
        row = self._query_one("SELECT * FROM purchase_orders WHERE id=?", (purchase_order_id,))
        return self._hydrate(row) if row else None

    def _hydrate(self, row: dict) -> PurchaseOrder:
        line_rows = self._query(
            "SELECT * FROM purchase_order_lines WHERE purchase_order_id=? ORDER BY id",
            (row["id"],))
        lines = [
            PurchaseOrderLine(
                id=lr["id"], product_id=lr["product_id"], description=lr["description"] or "",
                ordered_quantity=to_decimal(lr["ordered_quantity"]),
                unit_price=Money(to_decimal(lr["unit_price"]), lr["currency_code"]),
                conversion_factor=to_decimal(lr["conversion_factor"], "1"),
                received_quantity=to_decimal(lr["received_quantity"]),
                accepted_quantity=to_decimal(lr["accepted_quantity"]),
                rejected_quantity=to_decimal(lr["rejected_quantity"]),
                invoiced_quantity=to_decimal(lr["invoiced_quantity"]),
                destination_warehouse_id=lr["destination_warehouse_id"])
            for lr in line_rows
        ]
        return PurchaseOrder(
            id=row["id"], document_number=row["document_number"], supplier_id=row["supplier_id"],
            branch_id=row["branch_id"], warehouse_id=row["warehouse_id"],
            currency_code=row["currency_code"],
            purchase_type=PurchaseType(row["purchase_type"]),
            status=PurchaseOrderStatus(row["status"]), lines=lines, version=row["version"],
            created_by_user_id=row["created_by_user_id"],
            approved_by_user_id=row["approved_by_user_id"],
            created_at=row["created_at"], updated_at=row["updated_at"])
