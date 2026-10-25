"""Collection repository — cobros y sus aplicaciones a documentos (§11)."""

from __future__ import annotations

from datetime import date

from backend.domain.finance.entities.receivable import Collection, CollectionApplication
from backend.domain.finance.enums import CollectionStatus
from backend.domain.finance.value_objects.money import Money
from backend.infrastructure.db.repositories.finance.base import FinanceRepositoryBase


def _to_entity(row: dict) -> Collection:
    currency = row["currency_code"]
    return Collection(
        id=row["id"], customer_id=row["customer_id"],
        amount=Money.from_string(row["amount"], currency),
        applied_amount=Money.from_string(row["applied_amount"], currency),
        collection_date=date.fromisoformat(row["collection_date"]),
        treasury_account_id=row["treasury_account_id"],
        operation_id=row["operation_id"],
        payment_method=row["payment_method"],
        status=CollectionStatus(row["status"]),
        journal_entry_id=row["journal_entry_id"],
        reference=row["reference"], branch_id=row["branch_id"],
        created_by=row["created_by"],
        created_at=row["created_at"], updated_at=row["updated_at"],
    )


def _application_to_entity(row: dict) -> CollectionApplication:
    return CollectionApplication(
        id=row["id"], collection_id=row["collection_id"], receivable_id=row["receivable_id"],
        applied_amount=Money.from_string(row["applied_amount"], row["currency_code"]),
        operation_id=row["operation_id"], journal_entry_id=row["journal_entry_id"],
        created_by=row["created_by"], created_at=row["created_at"])


class CollectionRepository(FinanceRepositoryBase):
    def save(self, collection: Collection) -> None:
        self._insert("collections", {
            "id": collection.id, "customer_id": collection.customer_id,
            "branch_id": collection.branch_id,
            "treasury_account_id": collection.treasury_account_id,
            "payment_method": collection.payment_method,
            "currency_code": collection.amount.currency_code,
            "amount": collection.amount.to_string(),
            "applied_amount": collection.applied_amount.to_string(),
            "collection_date": collection.collection_date.isoformat(),
            "reference": collection.reference, "status": collection.status.value,
            "journal_entry_id": collection.journal_entry_id,
            "created_by": collection.created_by, "operation_id": collection.operation_id,
            "created_at": collection.created_at, "updated_at": collection.updated_at,
        })

    def update(self, collection: Collection) -> None:
        self._update("collections", {
            "applied_amount": collection.applied_amount.to_string(),
            "status": collection.status.value,
            "journal_entry_id": collection.journal_entry_id,
            "updated_at": collection.updated_at,
        }, where="id=?", params=(collection.id,))

    def get(self, collection_id: str) -> Collection | None:
        row = self._query_one("SELECT * FROM collections WHERE id=?", (collection_id,))
        return _to_entity(row) if row else None

    def find_by_operation_id(self, operation_id: str) -> Collection | None:
        row = self._query_one("SELECT * FROM collections WHERE operation_id=?", (operation_id,))
        return _to_entity(row) if row else None

    def list_with_unapplied(self, customer_id: str) -> list[Collection]:
        rows = self._query(
            "SELECT * FROM collections WHERE customer_id=?"
            " AND status IN ('UNAPPLIED','PARTIALLY_APPLIED') ORDER BY collection_date",
            (customer_id,))
        return [_to_entity(row) for row in rows]

    # ── aplicaciones ─────────────────────────────────────────────────────
    def save_application(self, application: CollectionApplication) -> None:
        self._insert("collection_applications", {
            "id": application.id, "collection_id": application.collection_id,
            "receivable_id": application.receivable_id,
            "applied_amount": application.applied_amount.to_string(),
            "currency_code": application.applied_amount.currency_code,
            "journal_entry_id": application.journal_entry_id,
            "created_by": application.created_by, "operation_id": application.operation_id,
            "created_at": application.created_at,
        })

    def find_application_by_operation_id(self, operation_id: str) -> CollectionApplication | None:
        row = self._query_one("SELECT * FROM collection_applications WHERE operation_id=?",
                              (operation_id,))
        return _application_to_entity(row) if row else None

    def list_applications(self, *, collection_id: str | None = None,
                          receivable_id: str | None = None) -> list[CollectionApplication]:
        if collection_id is not None:
            rows = self._query("SELECT * FROM collection_applications WHERE collection_id=?"
                               " ORDER BY created_at", (collection_id,))
        else:
            rows = self._query("SELECT * FROM collection_applications WHERE receivable_id=?"
                               " ORDER BY created_at", (receivable_id,))
        return [_application_to_entity(row) for row in rows]

    def list_by_receivable(self, receivable_id: str) -> list[Collection]:
        rows = self._query(
            "SELECT c.* FROM collections c JOIN collection_applications a"
            " ON a.collection_id = c.id WHERE a.receivable_id=? GROUP BY c.id"
            " ORDER BY c.collection_date", (receivable_id,))
        return [_to_entity(row) for row in rows]
