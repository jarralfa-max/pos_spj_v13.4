"""GoodsReceiptRepository — persists the GoodsReceipt aggregate (header + lines
+ discrepancies). Only accepted quantity is what later enters inventory (§38)."""

from __future__ import annotations

from datetime import date

from decimal import Decimal

from backend.domain.procurement.entities import (
    GoodsReceipt,
    GoodsReceiptLine,
    ReceiptDiscrepancy,
)
from backend.domain.procurement.enums import DiscrepancyType
from backend.infrastructure.db.repositories.procurement.base import (
    ProcurementRepositoryBase,
    dec_str,
    to_decimal,
)


class GoodsReceiptRepository(ProcurementRepositoryBase):
    def completed_for_document(self, *, purchase_order_id=None,
                               direct_purchase_id=None) -> list[GoodsReceipt]:
        field, value = ("purchase_order_id", purchase_order_id) if purchase_order_id else (
            "direct_purchase_id", direct_purchase_id)
        if not value:
            return []
        rows = self._query(
            f"SELECT id FROM goods_receipts WHERE {field}=? AND status='COMPLETED'",
            (value,))
        return [self.get(row["id"]) for row in rows]

    def accepted_by_product(self, *, purchase_order_id=None,
                            direct_purchase_id=None) -> dict[str, Decimal]:
        totals: dict[str, Decimal] = {}
        for receipt in self.completed_for_document(
                purchase_order_id=purchase_order_id,
                direct_purchase_id=direct_purchase_id):
            for line in receipt.lines:
                totals[line.product_id] = totals.get(line.product_id, Decimal("0")) + line.accepted_quantity
        return totals

    def accepted_by_source(self, *, purchase_order_id=None, direct_purchase_id=None
                           ) -> tuple[dict[str, Decimal], dict[str, Decimal]]:
        """Aceptado por LÍNEA del documento de compra, y aparte lo que se
        recibió sin línea ligada (recepciones previas a la FASE 11, compras
        rápidas), agrupado por producto para repartirlo después."""
        by_line: dict[str, Decimal] = {}
        unlinked: dict[str, Decimal] = {}
        for receipt in self.completed_for_document(
                purchase_order_id=purchase_order_id,
                direct_purchase_id=direct_purchase_id):
            for line in receipt.lines:
                if line.purchase_order_line_id:
                    key, bucket = line.purchase_order_line_id, by_line
                else:
                    key, bucket = line.product_id, unlinked
                bucket[key] = bucket.get(key, Decimal("0")) + line.accepted_quantity
        return by_line, unlinked

    def get_by_operation(self, operation_id: str) -> GoodsReceipt | None:
        row = self._query_one("SELECT id FROM goods_receipts WHERE operation_id=?",
                              (operation_id,))
        return self.get(row["id"]) if row else None

    def set_operation_id(self, goods_receipt_id: str, operation_id: str) -> None:
        self._execute("UPDATE goods_receipts SET operation_id=? WHERE id=?",
                      (operation_id, goods_receipt_id))

    def save(self, gr: GoodsReceipt) -> None:
        self._execute(
            "INSERT INTO goods_receipts (id, document_number, supplier_id, branch_id,"
            " warehouse_id, purchase_order_id, direct_purchase_id, status,"
            " received_by_user_id, operation_id, created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?)"
            " ON CONFLICT(id) DO UPDATE SET status=excluded.status",
            (gr.id, gr.document_number, gr.supplier_id, gr.branch_id, gr.warehouse_id,
             gr.purchase_order_id, gr.direct_purchase_id, gr.status,
             gr.received_by_user_id, None, gr.created_at))
        if gr.shipment_id:
            self._execute("UPDATE goods_receipts SET shipment_id=? WHERE id=?",
                          (gr.shipment_id, gr.id))
        self._save_children(
            "goods_receipt_lines", "goods_receipt_id", gr.id,
            ("id", "goods_receipt_id", "product_id", "ordered_quantity",
             "received_quantity", "accepted_quantity", "rejected_quantity", "lot",
             "expiration", "temperature", "net_weight", "piece_count",
             "purchase_order_line_id"),
            [(ln.id, gr.id, ln.product_id, dec_str(ln.ordered_quantity),
                 dec_str(ln.received_quantity), dec_str(ln.accepted_quantity),
                 dec_str(ln.rejected_quantity), ln.lot,
                 ln.expiration.isoformat() if ln.expiration else None,
                 dec_str(ln.temperature) if ln.temperature is not None else None,
                 dec_str(ln.net_weight) if ln.net_weight is not None else None,
                 str(ln.piece_count) if ln.piece_count is not None else None,
                 ln.purchase_order_line_id)
             for ln in gr.lines])
        self._execute("DELETE FROM receipt_discrepancies WHERE goods_receipt_id=?", (gr.id,))
        for d in gr.discrepancies:
            self._execute(
                "INSERT INTO receipt_discrepancies (id, goods_receipt_id,"
                " discrepancy_type, expected, actual, reason) VALUES (?,?,?,?,?,?)",
                (d.id, gr.id, d.discrepancy_type.value, dec_str(d.expected),
                 dec_str(d.actual), d.reason))

    def get_by_direct_purchase(self, direct_purchase_id: str) -> GoodsReceipt | None:
        row = self._query_one("SELECT id FROM goods_receipts WHERE direct_purchase_id=?",
                              (direct_purchase_id,))
        return self.get(row["id"]) if row else None

    def get(self, goods_receipt_id: str) -> GoodsReceipt | None:
        row = self._query_one("SELECT * FROM goods_receipts WHERE id=?", (goods_receipt_id,))
        if row is None:
            return None
        line_rows = self._query(
            "SELECT * FROM goods_receipt_lines WHERE goods_receipt_id=? ORDER BY id",
            (goods_receipt_id,))
        lines = [
            GoodsReceiptLine(
                id=lr["id"], product_id=lr["product_id"],
                ordered_quantity=to_decimal(lr["ordered_quantity"]),
                received_quantity=to_decimal(lr["received_quantity"]),
                accepted_quantity=to_decimal(lr["accepted_quantity"]),
                rejected_quantity=to_decimal(lr["rejected_quantity"]),
                lot=lr["lot"],
                # La caducidad se guardaba y NO se volvía a leer.
                expiration=(date.fromisoformat(lr["expiration"]) if lr.get("expiration")
                            else None),
                temperature=to_decimal(lr["temperature"]) if lr["temperature"] else None,
                net_weight=to_decimal(lr["net_weight"]) if lr.get("net_weight") else None,
                piece_count=int(lr["piece_count"]) if lr.get("piece_count") else None,
                purchase_order_line_id=lr.get("purchase_order_line_id") or None)
            for lr in line_rows
        ]
        disc_rows = self._query(
            "SELECT * FROM receipt_discrepancies WHERE goods_receipt_id=? ORDER BY id",
            (goods_receipt_id,))
        discrepancies = [
            ReceiptDiscrepancy(
                id=dr["id"], discrepancy_type=DiscrepancyType(dr["discrepancy_type"]),
                expected=to_decimal(dr["expected"]), actual=to_decimal(dr["actual"]),
                reason=dr["reason"] or "")
            for dr in disc_rows
        ]
        return GoodsReceipt(
            id=row["id"], document_number=row["document_number"],
            supplier_id=row["supplier_id"], branch_id=row["branch_id"],
            warehouse_id=row["warehouse_id"], purchase_order_id=row["purchase_order_id"],
            direct_purchase_id=row["direct_purchase_id"], status=row["status"],
            lines=lines, discrepancies=discrepancies,
            received_by_user_id=row["received_by_user_id"], created_at=row["created_at"])
