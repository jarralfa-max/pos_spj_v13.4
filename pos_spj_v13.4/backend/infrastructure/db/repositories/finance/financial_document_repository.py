"""FinancialDocument repository."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from backend.domain.finance.entities.financial_document import FinancialDocument
from backend.domain.finance.enums import FinancialDocumentStatus, FinancialDocumentType
from backend.domain.finance.value_objects.money import Money
from backend.infrastructure.db.repositories.finance.base import FinanceRepositoryBase

_COLUMNS = ("id, document_type, document_number, issue_date, due_date, currency_code,"
            " exchange_rate, subtotal, tax_amount, discount_amount, total_amount,"
            " outstanding_amount, status, branch_id, customer_id, supplier_id,"
            " source_module, source_document_id, operation_id, created_at, updated_at")


def _money(value: str | None, currency: str) -> Money | None:
    return Money.from_string(value, currency) if value is not None else None


def _to_entity(row: dict) -> FinancialDocument:
    currency = row["currency_code"]
    return FinancialDocument(
        id=row["id"],
        document_type=FinancialDocumentType(row["document_type"]),
        document_number=row["document_number"],
        issue_date=date.fromisoformat(row["issue_date"]),
        due_date=date.fromisoformat(row["due_date"]) if row["due_date"] else None,
        exchange_rate=Decimal(row["exchange_rate"]),
        subtotal=_money(row["subtotal"], currency),
        tax_amount=_money(row["tax_amount"], currency),
        discount_amount=_money(row["discount_amount"], currency),
        total_amount=Money.from_string(row["total_amount"], currency),
        outstanding_amount=Money.from_string(row["outstanding_amount"], currency),
        status=FinancialDocumentStatus(row["status"]),
        branch_id=row["branch_id"],
        customer_id=row["customer_id"],
        supplier_id=row["supplier_id"],
        source_module=row["source_module"],
        source_document_id=row["source_document_id"],
        operation_id=row["operation_id"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


class FinancialDocumentRepository(FinanceRepositoryBase):
    def save(self, document: FinancialDocument) -> None:
        self._execute(
            f"INSERT INTO financial_documents ({_COLUMNS})"
            " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (document.id, document.document_type.value, document.document_number,
             document.issue_date.isoformat(),
             document.due_date.isoformat() if document.due_date else None,
             document.currency_code, str(document.exchange_rate),
             document.subtotal.to_string() if document.subtotal else None,
             document.tax_amount.to_string() if document.tax_amount else None,
             document.discount_amount.to_string() if document.discount_amount else None,
             document.total_amount.to_string(), document.outstanding_amount.to_string(),
             document.status.value, document.branch_id, document.customer_id,
             document.supplier_id, document.source_module, document.source_document_id,
             document.operation_id, document.created_at, document.updated_at),
        )

    def update(self, document: FinancialDocument) -> None:
        self._execute(
            "UPDATE financial_documents SET outstanding_amount=?, status=?, updated_at=?"
            " WHERE id=?",
            (document.outstanding_amount.to_string(), document.status.value,
             document.updated_at, document.id),
        )

    def get(self, document_id: str) -> FinancialDocument | None:
        row = self._query_one(
            f"SELECT {_COLUMNS} FROM financial_documents WHERE id=?", (document_id,)
        )
        return _to_entity(row) if row else None

    def find_by_source(self, source_module: str, source_document_id: str) -> list[FinancialDocument]:
        rows = self._query(
            f"SELECT {_COLUMNS} FROM financial_documents"
            " WHERE source_module=? AND source_document_id=?",
            (source_module, source_document_id),
        )
        return [_to_entity(row) for row in rows]

    def find_by_operation_id(self, operation_id: str) -> FinancialDocument | None:
        row = self._query_one(
            f"SELECT {_COLUMNS} FROM financial_documents WHERE operation_id=?", (operation_id,)
        )
        return _to_entity(row) if row else None
