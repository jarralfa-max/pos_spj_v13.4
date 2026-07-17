"""DirectPurchaseRepository — persists the DirectPurchase aggregate (header + lines).

The aggregate is saved atomically by the UnitOfWork. Money/quantity columns are
decimal strings; the id is a UUIDv7. Confirmed documents stay immutable — the
repository never mutates history, it replaces the line set only while editable.
"""

from __future__ import annotations

from decimal import Decimal

from backend.domain.procurement.entities import DirectPurchase, DirectPurchaseLine
from backend.domain.procurement.enums import (
    DirectPurchaseMode,
    DocumentStatus,
    PaymentCondition,
    PurchaseType,
    SourceChannel,
)
from backend.domain.procurement.value_objects import Money
from backend.infrastructure.db.repositories.procurement.base import (
    ProcurementRepositoryBase,
    dec_str,
    to_decimal,
)


class DirectPurchaseRepository(ProcurementRepositoryBase):
    def save(self, dp: DirectPurchase) -> None:
        self._execute(
            "INSERT INTO direct_purchases (id, document_number, supplier_id, branch_id,"
            " warehouse_id, mode, payment_condition, currency_code, source_channel,"
            " purchase_type, status, subtotal, tax_total, total, payment_source,"
            " created_by_user_id, authorized_by_user_id, authorization_reason,"
            " operation_id, goods_receipt_id, payable_id, payment_instruction_id,"
            " created_at, updated_at)"
            " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)"
            " ON CONFLICT(id) DO UPDATE SET"
            " status=excluded.status, subtotal=excluded.subtotal,"
            " tax_total=excluded.tax_total, total=excluded.total,"
            " payment_source=excluded.payment_source,"
            " authorized_by_user_id=excluded.authorized_by_user_id,"
            " authorization_reason=excluded.authorization_reason,"
            " goods_receipt_id=excluded.goods_receipt_id, payable_id=excluded.payable_id,"
            " payment_instruction_id=excluded.payment_instruction_id,"
            " updated_at=excluded.updated_at",
            (dp.id, dp.document_number, dp.supplier_id, dp.branch_id, dp.warehouse_id,
             dp.mode.value, dp.payment_condition.value, dp.currency_code,
             dp.source_channel.value, dp.purchase_type.value, dp.status.value,
             dec_str(dp.subtotal().amount), dec_str(dp.tax_total().amount),
             dec_str(dp.total().amount),
             dp.payment_instruction.source.value if dp.payment_instruction else None,
             dp.created_by_user_id, dp.authorized_by_user_id, dp.authorization_reason,
             None, None, None,
             dp.payment_instruction.id if dp.payment_instruction else None,
             dp.created_at, dp.updated_at))
        self._replace_lines(dp)

    def _replace_lines(self, dp: DirectPurchase) -> None:
        self._execute("DELETE FROM direct_purchase_lines WHERE direct_purchase_id=?", (dp.id,))
        for ln in dp.lines:
            self._execute(
                "INSERT INTO direct_purchase_lines (id, direct_purchase_id, product_id,"
                " description, quantity, unit_cost, currency_code, purchase_unit,"
                " inventory_unit, conversion_factor, discount, tax, line_total,"
                " destination_branch_id, destination_warehouse_id)"
                " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (ln.id, dp.id, ln.product_id, ln.description, dec_str(ln.quantity),
                 dec_str(ln.unit_cost.amount), ln.unit_cost.currency_code, ln.purchase_unit,
                 ln.inventory_unit, dec_str(ln.conversion_factor), dec_str(ln.discount.amount),
                 dec_str(ln.tax.amount), dec_str(ln.line_total().amount),
                 ln.destination_branch_id, ln.destination_warehouse_id))

    def link_receipt(self, direct_purchase_id: str, goods_receipt_id: str) -> None:
        self._execute("UPDATE direct_purchases SET goods_receipt_id=? WHERE id=?",
                      (goods_receipt_id, direct_purchase_id))

    def link_payable(self, direct_purchase_id: str, payable_id: str) -> None:
        self._execute("UPDATE direct_purchases SET payable_id=? WHERE id=?",
                      (payable_id, direct_purchase_id))

    def get(self, direct_purchase_id: str) -> DirectPurchase | None:
        row = self._query_one("SELECT * FROM direct_purchases WHERE id=?", (direct_purchase_id,))
        if row is None:
            return None
        return self._hydrate(row)

    def get_by_operation(self, operation_id: str) -> DirectPurchase | None:
        row = self._query_one("SELECT * FROM direct_purchases WHERE operation_id=?",
                              (operation_id,))
        return self._hydrate(row) if row else None

    def _hydrate(self, row: dict) -> DirectPurchase:
        currency = row["currency_code"]
        line_rows = self._query(
            "SELECT * FROM direct_purchase_lines WHERE direct_purchase_id=? ORDER BY id",
            (row["id"],))
        lines = [
            DirectPurchaseLine(
                id=lr["id"], product_id=lr["product_id"], description=lr["description"] or "",
                quantity=to_decimal(lr["quantity"]),
                unit_cost=Money(to_decimal(lr["unit_cost"]), lr["currency_code"]),
                purchase_unit=lr["purchase_unit"], inventory_unit=lr["inventory_unit"],
                conversion_factor=to_decimal(lr["conversion_factor"], "1"),
                discount=Money(to_decimal(lr["discount"]), lr["currency_code"]),
                tax=Money(to_decimal(lr["tax"]), lr["currency_code"]),
                destination_branch_id=lr["destination_branch_id"],
                destination_warehouse_id=lr["destination_warehouse_id"])
            for lr in line_rows
        ]
        return DirectPurchase(
            id=row["id"], document_number=row["document_number"],
            supplier_id=row["supplier_id"], branch_id=row["branch_id"],
            warehouse_id=row["warehouse_id"], mode=DirectPurchaseMode(row["mode"]),
            payment_condition=PaymentCondition(row["payment_condition"]),
            currency_code=currency, source_channel=SourceChannel(row["source_channel"]),
            purchase_type=PurchaseType(row["purchase_type"]),
            status=DocumentStatus(row["status"]), lines=lines,
            created_by_user_id=row["created_by_user_id"],
            authorized_by_user_id=row["authorized_by_user_id"],
            authorization_reason=row["authorization_reason"] or "",
            created_at=row["created_at"], updated_at=row["updated_at"])

    def set_operation_id(self, direct_purchase_id: str, operation_id: str) -> None:
        self._execute("UPDATE direct_purchases SET operation_id=? WHERE id=?",
                      (operation_id, direct_purchase_id))

    def record_authorization(self, *, direct_purchase_id: str, requested_by_user_id: str,
                             authorized_by_user_id: str, permission_code: str,
                             reason: str, amount: Decimal, currency_code: str = "MXN",
                             terminal_id: str | None = None, operation_id: str | None = None,
                             authorization_id: str, created_at: str) -> None:
        self._execute(
            "INSERT INTO direct_purchase_authorizations (id, direct_purchase_id,"
            " requested_by_user_id, authorized_by_user_id, permission_code, reason,"
            " amount, terminal_id, operation_id, created_at)"
            " VALUES (?,?,?,?,?,?,?,?,?,?)",
            (authorization_id, direct_purchase_id, requested_by_user_id,
             authorized_by_user_id, permission_code, reason, dec_str(amount),
             terminal_id, operation_id, created_at))
