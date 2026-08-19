"""SaleRepository — persists/reconstructs the `Sale` aggregate (with its
`SaleLine`s) against the `sales`/`sale_lines` tables from
backend/infrastructure/db/schema/sales_schema.py.

Concrete class, no `Protocol` port — mirrors the Inventory family's
convention (backend/domain/inventory/ has no repository_ports.py either),
the strongest precedent for this bounded context since sales_schema.py's own
docstring says it follows inventory_schema.py's conventions exactly. (A
`Protocol`-port family also exists elsewhere in this repo — transfers,
customers, crm — but is not the more specific precedent here.)

`save()` replaces all of a sale's lines wholesale on every call (matches
backend/infrastructure/db/repositories/procurement/purchase_order_repository.py's
`save()`: delete-then-reinsert, not a line-by-line diff/upsert) — simpler and
safer given `Sale.remove_line()` means a line is genuinely gone, not merely
zeroed. `get()` does two separate queries (header, then lines ordered by
creation) — no JOIN, matching the same repository's `_hydrate` shape.

Never commits — SalesUnitOfWork owns the transaction boundary.
"""

from __future__ import annotations

import json

from backend.domain.sales.entities import Sale, SaleInvoiceRequest, SaleLine
from backend.domain.sales.enums import InvoiceStatus, PaymentMethod, SaleStatus
from backend.domain.sales.value_objects.quantity import Quantity
from backend.domain.sales.value_objects.sale_payment import SalePayment
from backend.domain.sales.value_objects.sale_return import SaleReturn
from backend.domain.sales.value_objects.sale_totals import SaleTotals
from backend.infrastructure.db.repositories.sales.base import (
    SalesRepositoryBase,
    dec_str,
    enum_value,
    to_decimal,
)


def _snapshot_to_json(snapshot) -> str:
    return json.dumps(dict(snapshot or {}), ensure_ascii=False, sort_keys=True,
                       separators=(",", ":"))


def _snapshot_from_json(raw: str | None) -> dict:
    if not raw:
        return {}
    return json.loads(raw)


class SaleRepository(SalesRepositoryBase):
    def save(self, sale: Sale) -> None:
        self._execute(
            """
            INSERT INTO sales (
                id, branch_id, cashier_user_id, operation_id, status, sale_number,
                workstation_id, cash_session_id, customer_id, channel, currency_code,
                gross_subtotal, discount_total, promotion_total, coupon_total,
                loyalty_total, tax_total, rounding_adjustment, total,
                sale_level_discount, loyalty_redeemed_amount, version, created_at, suspended_at,
                completed_at, cancelled_at, reversed_at, suspended_by_user_id,
                suspended_workstation_id, inventory_reservation_id
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            ON CONFLICT(id) DO UPDATE SET
                status=excluded.status,
                sale_number=excluded.sale_number,
                workstation_id=excluded.workstation_id,
                cash_session_id=excluded.cash_session_id,
                customer_id=excluded.customer_id,
                channel=excluded.channel,
                currency_code=excluded.currency_code,
                gross_subtotal=excluded.gross_subtotal,
                discount_total=excluded.discount_total,
                promotion_total=excluded.promotion_total,
                coupon_total=excluded.coupon_total,
                loyalty_total=excluded.loyalty_total,
                tax_total=excluded.tax_total,
                rounding_adjustment=excluded.rounding_adjustment,
                total=excluded.total,
                sale_level_discount=excluded.sale_level_discount,
                loyalty_redeemed_amount=excluded.loyalty_redeemed_amount,
                version=excluded.version,
                suspended_at=excluded.suspended_at,
                completed_at=excluded.completed_at,
                cancelled_at=excluded.cancelled_at,
                reversed_at=excluded.reversed_at,
                suspended_by_user_id=excluded.suspended_by_user_id,
                suspended_workstation_id=excluded.suspended_workstation_id,
                inventory_reservation_id=excluded.inventory_reservation_id
            """,
            (
                sale.id, sale.branch_id, sale.cashier_user_id, sale.operation_id,
                enum_value(sale.status), sale.sale_number,
                sale.workstation_id, sale.cash_session_id, sale.customer_id,
                sale.channel, sale.currency_code,
                dec_str(sale.totals.gross_subtotal), dec_str(sale.totals.discount_total),
                dec_str(sale.totals.promotion_total), dec_str(sale.totals.coupon_total),
                dec_str(sale.totals.loyalty_total), dec_str(sale.totals.tax_total),
                dec_str(sale.totals.rounding_adjustment), dec_str(sale.totals.total),
                dec_str(sale.sale_level_discount), dec_str(sale.loyalty_redeemed_amount),
                sale.version, sale.created_at,
                sale.suspended_at, sale.completed_at, sale.cancelled_at, sale.reversed_at,
                sale.suspended_by_user_id, sale.suspended_workstation_id,
                sale.inventory_reservation_id,
            ),
        )
        self._execute("DELETE FROM sale_lines WHERE sale_id=?", (sale.id,))
        for line in sale.lines:
            self._execute(
                """
                INSERT INTO sale_lines (
                    id, sale_id, product_id, product_snapshot, quantity, quantity_unit,
                    unit_price, pricing_snapshot_id, discount_total, tax_total,
                    weight_source, lot_reference, created_at, updated_at
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    line.id, line.sale_id, line.product_id,
                    _snapshot_to_json(line.product_snapshot),
                    dec_str(line.quantity.value), line.quantity.unit,
                    dec_str(line.unit_price), line.pricing_snapshot_id,
                    dec_str(line.discount_total), dec_str(line.tax_total),
                    line.weight_source, line.lot_reference,
                    line.created_at, line.updated_at,
                ),
            )
        self._execute("DELETE FROM sale_payments WHERE sale_id=?", (sale.id,))
        for payment in sale.payments:
            self._execute(
                """
                INSERT INTO sale_payments (
                    id, sale_id, method, amount, reference, captured_by_user_id, captured_at
                ) VALUES (?,?,?,?,?,?,?)
                """,
                (
                    payment.id, payment.sale_id, enum_value(payment.method),
                    dec_str(payment.amount), payment.reference,
                    payment.captured_by_user_id, payment.captured_at,
                ),
            )
        self._execute("DELETE FROM sale_returns WHERE sale_id=?", (sale.id,))
        for sale_return in sale.returns:
            self._execute(
                """
                INSERT INTO sale_returns (
                    id, sale_id, line_id, quantity, amount, reason,
                    requested_by_user_id, authorized_by_user_id, created_at
                ) VALUES (?,?,?,?,?,?,?,?,?)
                """,
                (
                    sale_return.id, sale_return.sale_id, sale_return.line_id,
                    dec_str(sale_return.quantity), dec_str(sale_return.amount),
                    sale_return.reason, sale_return.requested_by_user_id,
                    sale_return.authorized_by_user_id, sale_return.created_at,
                ),
            )
        self._execute("DELETE FROM sale_invoice_requests WHERE sale_id=?", (sale.id,))
        for invoice in sale.invoice_requests:
            self._execute(
                """
                INSERT INTO sale_invoice_requests (
                    id, sale_id, tax_identifier, legal_name, cfdi_use, requested_by_user_id,
                    status, uuid_fiscal, error_message, requested_at, updated_at
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    invoice.id, invoice.sale_id, invoice.tax_identifier, invoice.legal_name,
                    invoice.cfdi_use, invoice.requested_by_user_id, enum_value(invoice.status),
                    invoice.uuid_fiscal, invoice.error_message, invoice.requested_at,
                    invoice.updated_at,
                ),
            )

    def get(self, sale_id: str) -> Sale | None:
        row = self._query_one("SELECT * FROM sales WHERE id=?", (sale_id,))
        if row is None:
            return None
        return self._hydrate(row)

    def get_by_operation_id(self, operation_id: str) -> Sale | None:
        row = self._query_one("SELECT * FROM sales WHERE operation_id=?", (operation_id,))
        if row is None:
            return None
        return self._hydrate(row)

    def operation_exists(self, operation_id: str) -> bool:
        return self._scalar(
            "SELECT 1 FROM sales WHERE operation_id=?", (operation_id,)) is not None

    def count_suspended(self, *, branch_id: str, workstation_id: str | None = None) -> int:
        """§41: how many sales this branch/workstation currently holds
        SUSPENDED — the cross-aggregate count `SaleSuspensionPolicy` needs
        before `Sale.suspend()` can run (a pure domain policy can't query)."""
        if workstation_id is not None:
            return self._scalar(
                "SELECT COUNT(*) FROM sales WHERE status='SUSPENDED' AND branch_id=?"
                " AND suspended_workstation_id=?", (branch_id, workstation_id), default=0)
        return self._scalar(
            "SELECT COUNT(*) FROM sales WHERE status='SUSPENDED' AND branch_id=?",
            (branch_id,), default=0)

    def list_suspended_before(self, cutoff_iso: str) -> list[Sale]:
        """POS-15/§41: every SUSPENDED sale (any branch/workstation) held
        since before `cutoff_iso` — the system-wide sweep
        `ExpireSuspendedSalesUseCase` needs. Cross-branch by design (a
        sweep, not a per-cashier query) — mirrors
        `ExpireOrphanedInventoryReservationsUseCase`'s own "maintenance
        hook, not a per-branch user action" shape, one level up since
        Sales itself (unlike `StockReservationService`) isn't constructed
        per-branch."""
        rows = self._query(
            "SELECT * FROM sales WHERE status='SUSPENDED' AND suspended_at < ?"
            " ORDER BY suspended_at", (cutoff_iso,))
        return [self._hydrate(row) for row in rows]

    def list_suspended(self, *, branch_id: str, workstation_id: str | None = None) -> list[Sale]:
        if workstation_id is not None:
            rows = self._query(
                "SELECT * FROM sales WHERE status='SUSPENDED' AND branch_id=?"
                " AND suspended_workstation_id=? ORDER BY suspended_at",
                (branch_id, workstation_id))
        else:
            rows = self._query(
                "SELECT * FROM sales WHERE status='SUSPENDED' AND branch_id=?"
                " ORDER BY suspended_at", (branch_id,))
        return [self._hydrate(row) for row in rows]

    def _hydrate(self, row: dict) -> Sale:
        line_rows = self._query(
            "SELECT * FROM sale_lines WHERE sale_id=? ORDER BY created_at", (row["id"],))
        lines = [self._hydrate_line(line_row) for line_row in line_rows]
        payment_rows = self._query(
            "SELECT * FROM sale_payments WHERE sale_id=? ORDER BY captured_at", (row["id"],))
        payments = [self._hydrate_payment(payment_row) for payment_row in payment_rows]
        return_rows = self._query(
            "SELECT * FROM sale_returns WHERE sale_id=? ORDER BY created_at", (row["id"],))
        returns = [self._hydrate_return(return_row) for return_row in return_rows]
        invoice_rows = self._query(
            "SELECT * FROM sale_invoice_requests WHERE sale_id=? ORDER BY requested_at",
            (row["id"],))
        invoice_requests = [self._hydrate_invoice_request(r) for r in invoice_rows]
        totals = SaleTotals(
            gross_subtotal=to_decimal(row["gross_subtotal"]),
            discount_total=to_decimal(row["discount_total"]),
            promotion_total=to_decimal(row["promotion_total"]),
            coupon_total=to_decimal(row["coupon_total"]),
            loyalty_total=to_decimal(row["loyalty_total"]),
            tax_total=to_decimal(row["tax_total"]),
            rounding_adjustment=to_decimal(row["rounding_adjustment"]),
            total=to_decimal(row["total"]),
        )
        return Sale(
            id=row["id"], branch_id=row["branch_id"], cashier_user_id=row["cashier_user_id"],
            operation_id=row["operation_id"], status=SaleStatus(row["status"]),
            sale_number=row["sale_number"], workstation_id=row["workstation_id"],
            cash_session_id=row["cash_session_id"], customer_id=row["customer_id"],
            channel=row["channel"], currency_code=row["currency_code"],
            lines=lines, payments=payments, returns=returns,
            invoice_requests=invoice_requests, totals=totals,
            created_at=row["created_at"],
            suspended_at=row["suspended_at"], completed_at=row["completed_at"],
            cancelled_at=row["cancelled_at"], reversed_at=row["reversed_at"],
            version=row["version"],
            sale_level_discount=to_decimal(row["sale_level_discount"]),
            loyalty_redeemed_amount=to_decimal(row["loyalty_redeemed_amount"]),
            suspended_by_user_id=row["suspended_by_user_id"],
            suspended_workstation_id=row["suspended_workstation_id"],
            inventory_reservation_id=row["inventory_reservation_id"],
        )

    @staticmethod
    def _hydrate_line(row: dict) -> SaleLine:
        return SaleLine(
            id=row["id"], sale_id=row["sale_id"], product_id=row["product_id"],
            quantity=Quantity(to_decimal(row["quantity"]), row["quantity_unit"]),
            unit_price=to_decimal(row["unit_price"]),
            product_snapshot=_snapshot_from_json(row["product_snapshot"]),
            pricing_snapshot_id=row["pricing_snapshot_id"],
            discount_total=to_decimal(row["discount_total"]),
            tax_total=to_decimal(row["tax_total"]),
            weight_source=row["weight_source"], lot_reference=row["lot_reference"],
            created_at=row["created_at"], updated_at=row["updated_at"],
        )

    @staticmethod
    def _hydrate_payment(row: dict) -> SalePayment:
        return SalePayment(
            id=row["id"], sale_id=row["sale_id"], method=PaymentMethod(row["method"]),
            amount=to_decimal(row["amount"]), reference=row["reference"],
            captured_by_user_id=row["captured_by_user_id"], captured_at=row["captured_at"],
        )

    @staticmethod
    def _hydrate_return(row: dict) -> SaleReturn:
        return SaleReturn(
            id=row["id"], sale_id=row["sale_id"], line_id=row["line_id"],
            quantity=to_decimal(row["quantity"]), amount=to_decimal(row["amount"]),
            reason=row["reason"], requested_by_user_id=row["requested_by_user_id"],
            authorized_by_user_id=row["authorized_by_user_id"], created_at=row["created_at"],
        )

    @staticmethod
    def _hydrate_invoice_request(row: dict) -> SaleInvoiceRequest:
        return SaleInvoiceRequest(
            id=row["id"], sale_id=row["sale_id"], tax_identifier=row["tax_identifier"],
            legal_name=row["legal_name"], cfdi_use=row["cfdi_use"],
            requested_by_user_id=row["requested_by_user_id"],
            status=InvoiceStatus(row["status"]), uuid_fiscal=row["uuid_fiscal"],
            error_message=row["error_message"], requested_at=row["requested_at"],
            updated_at=row["updated_at"],
        )
