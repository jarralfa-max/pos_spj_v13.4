"""PurchaseReturnRepository — persists the PurchaseReturn aggregate (header +
lines). A return references but never deletes the original goods receipt."""

from __future__ import annotations

from backend.domain.procurement.entities import PurchaseReturn, PurchaseReturnLine
from backend.domain.procurement.enums import PurchaseReturnReason, PurchaseReturnStatus
from backend.domain.procurement.value_objects import Money
from backend.infrastructure.db.repositories.procurement.base import (
    ProcurementRepositoryBase,
    dec_str,
    to_decimal,
)


class PurchaseReturnRepository(ProcurementRepositoryBase):
    def save(self, pr: PurchaseReturn) -> None:
        self._execute(
            "INSERT INTO purchase_returns (id, document_number, supplier_id, branch_id,"
            " warehouse_id, goods_receipt_id, purchase_order_id, reason, status,"
            " created_by_user_id, operation_id, created_at, confirmed_at)"
            " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)"
            " ON CONFLICT(id) DO UPDATE SET status=excluded.status,"
            " confirmed_at=excluded.confirmed_at",
            (pr.id, pr.document_number, pr.supplier_id, pr.branch_id, pr.warehouse_id,
             pr.goods_receipt_id, pr.purchase_order_id, pr.reason.value, pr.status.value,
             pr.created_by_user_id, None, pr.created_at, pr.confirmed_at))
        self._execute("DELETE FROM purchase_return_lines WHERE purchase_return_id=?", (pr.id,))
        for ln in pr.lines:
            self._execute(
                "INSERT INTO purchase_return_lines (id, purchase_return_id, product_id,"
                " quantity, unit_cost, lot, goods_receipt_line_id, notes)"
                " VALUES (?,?,?,?,?,?,?,?)",
                (ln.id, pr.id, ln.product_id, dec_str(ln.quantity),
                 dec_str(ln.unit_cost.amount) if ln.unit_cost else None, ln.lot,
                 ln.goods_receipt_line_id, ln.notes))

    def set_operation_id(self, purchase_return_id: str, operation_id: str) -> None:
        self._execute("UPDATE purchase_returns SET operation_id=? WHERE id=?",
                      (operation_id, purchase_return_id))

    def get_by_operation(self, operation_id: str) -> PurchaseReturn | None:
        row = self._query_one("SELECT * FROM purchase_returns WHERE operation_id=?",
                              (operation_id,))
        return self._hydrate(row) if row else None

    def get(self, purchase_return_id: str) -> PurchaseReturn | None:
        row = self._query_one("SELECT * FROM purchase_returns WHERE id=?",
                              (purchase_return_id,))
        return self._hydrate(row) if row else None

    def list_by_supplier(self, supplier_id: str) -> list[PurchaseReturn]:
        rows = self._query(
            "SELECT id FROM purchase_returns WHERE supplier_id=? ORDER BY created_at DESC",
            (supplier_id,))
        return [self.get(row["id"]) for row in rows]

    def list_by_goods_receipt(self, goods_receipt_id: str) -> list[PurchaseReturn]:
        rows = self._query(
            "SELECT id FROM purchase_returns WHERE goods_receipt_id=? ORDER BY created_at",
            (goods_receipt_id,))
        return [self.get(row["id"]) for row in rows]

    def _hydrate(self, row: dict) -> PurchaseReturn:
        line_rows = self._query(
            "SELECT * FROM purchase_return_lines WHERE purchase_return_id=? ORDER BY id",
            (row["id"],))
        lines = [
            PurchaseReturnLine(
                id=lr["id"], product_id=lr["product_id"], quantity=to_decimal(lr["quantity"]),
                unit_cost=(Money(to_decimal(lr["unit_cost"])) if lr["unit_cost"] else None),
                lot=lr["lot"], goods_receipt_line_id=lr["goods_receipt_line_id"],
                notes=lr["notes"] or "")
            for lr in line_rows
        ]
        return PurchaseReturn(
            id=row["id"], document_number=row["document_number"],
            supplier_id=row["supplier_id"], branch_id=row["branch_id"],
            warehouse_id=row["warehouse_id"], reason=PurchaseReturnReason(row["reason"]),
            status=PurchaseReturnStatus(row["status"]),
            goods_receipt_id=row["goods_receipt_id"],
            purchase_order_id=row["purchase_order_id"], lines=lines,
            created_by_user_id=row["created_by_user_id"], created_at=row["created_at"],
            confirmed_at=row["confirmed_at"])
