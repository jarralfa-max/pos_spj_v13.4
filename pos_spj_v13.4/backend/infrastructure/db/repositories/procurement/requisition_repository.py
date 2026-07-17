"""PurchaseRequisitionRepository — persists the requisition aggregate (header +
lines). Requisitions are the enterprise entry point: the POS/forecast/minimum
stock emit a need, Compras turns it into a requisition, approval sources it."""

from __future__ import annotations

from datetime import date

from backend.domain.procurement.entities import PurchaseRequisition, RequisitionLine
from backend.domain.procurement.enums import PurchaseType, RequisitionStatus, SourceChannel
from backend.domain.procurement.value_objects import Money
from backend.infrastructure.db.repositories.procurement.base import (
    ProcurementRepositoryBase,
    dec_str,
    to_decimal,
)


def _to_date(value):
    return date.fromisoformat(value) if value else None


class PurchaseRequisitionRepository(ProcurementRepositoryBase):
    def save(self, req: PurchaseRequisition) -> None:
        self._execute(
            "INSERT INTO purchase_requisitions (id, document_number, branch_id,"
            " requested_by_user_id, purchase_type, priority, business_reason,"
            " required_date, status, source_channel, source_reference_id,"
            " approved_by_user_id, operation_id, created_at, updated_at)"
            " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)"
            " ON CONFLICT(id) DO UPDATE SET status=excluded.status,"
            " priority=excluded.priority, business_reason=excluded.business_reason,"
            " required_date=excluded.required_date,"
            " approved_by_user_id=excluded.approved_by_user_id,"
            " updated_at=excluded.updated_at",
            (req.id, req.document_number, req.branch_id, req.requested_by_user_id,
             req.purchase_type.value, req.priority, req.business_reason,
             req.required_date.isoformat() if req.required_date else None,
             req.status.value, req.source_channel.value, req.source_reference_id,
             req.approved_by_user_id, None, req.created_at, req.updated_at))
        self._execute("DELETE FROM purchase_requisition_lines WHERE requisition_id=?", (req.id,))
        for ln in req.lines:
            self._execute(
                "INSERT INTO purchase_requisition_lines (id, requisition_id, product_id,"
                " quantity, estimated_unit_cost, currency_code, required_date)"
                " VALUES (?,?,?,?,?,?,?)",
                (ln.id, req.id, ln.product_id, dec_str(ln.quantity),
                 dec_str(ln.estimated_unit_cost.amount) if ln.estimated_unit_cost else None,
                 ln.estimated_unit_cost.currency_code if ln.estimated_unit_cost else "MXN",
                 ln.required_date.isoformat() if ln.required_date else None))

    def set_operation_id(self, requisition_id: str, operation_id: str) -> None:
        self._execute("UPDATE purchase_requisitions SET operation_id=? WHERE id=?",
                      (operation_id, requisition_id))

    def get_by_operation(self, operation_id: str) -> PurchaseRequisition | None:
        row = self._query_one("SELECT * FROM purchase_requisitions WHERE operation_id=?",
                              (operation_id,))
        return self._hydrate(row) if row else None

    def get(self, requisition_id: str) -> PurchaseRequisition | None:
        row = self._query_one("SELECT * FROM purchase_requisitions WHERE id=?",
                              (requisition_id,))
        return self._hydrate(row) if row else None

    def _hydrate(self, row: dict) -> PurchaseRequisition:
        line_rows = self._query(
            "SELECT * FROM purchase_requisition_lines WHERE requisition_id=? ORDER BY id",
            (row["id"],))
        lines = [
            RequisitionLine(
                id=lr["id"], product_id=lr["product_id"], quantity=to_decimal(lr["quantity"]),
                estimated_unit_cost=(Money(to_decimal(lr["estimated_unit_cost"]),
                                           lr["currency_code"])
                                     if lr["estimated_unit_cost"] else None),
                required_date=_to_date(lr["required_date"]))
            for lr in line_rows
        ]
        return PurchaseRequisition(
            id=row["id"], document_number=row["document_number"], branch_id=row["branch_id"],
            requested_by_user_id=row["requested_by_user_id"],
            purchase_type=PurchaseType(row["purchase_type"]),
            status=RequisitionStatus(row["status"]), priority=row["priority"],
            business_reason=row["business_reason"] or "",
            required_date=_to_date(row["required_date"]),
            source_channel=SourceChannel(row["source_channel"]),
            source_reference_id=row["source_reference_id"], lines=lines,
            approved_by_user_id=row["approved_by_user_id"],
            created_at=row["created_at"], updated_at=row["updated_at"])
