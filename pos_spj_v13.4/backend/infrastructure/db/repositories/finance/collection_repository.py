"""Collection repository."""

from __future__ import annotations

from datetime import date

from backend.domain.finance.entities.receivable import Collection
from backend.domain.finance.value_objects.money import Money
from backend.infrastructure.db.repositories.finance.base import FinanceRepositoryBase

_COLUMNS = ("id, receivable_id, customer_id, amount, currency_code, collection_date,"
            " treasury_account_id, journal_entry_id, reference, branch_id, operation_id,"
            " created_at")


def _to_entity(row: dict) -> Collection:
    return Collection(
        id=row["id"], receivable_id=row["receivable_id"], customer_id=row["customer_id"],
        amount=Money.from_string(row["amount"], row["currency_code"]),
        collection_date=date.fromisoformat(row["collection_date"]),
        treasury_account_id=row["treasury_account_id"],
        operation_id=row["operation_id"],
        journal_entry_id=row["journal_entry_id"],
        reference=row["reference"], branch_id=row["branch_id"],
        created_at=row["created_at"],
    )


class CollectionRepository(FinanceRepositoryBase):
    def save(self, collection: Collection) -> None:
        self._execute(
            f"INSERT INTO collections ({_COLUMNS}) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
            (collection.id, collection.receivable_id, collection.customer_id,
             collection.amount.to_string(), collection.amount.currency_code,
             collection.collection_date.isoformat(), collection.treasury_account_id,
             collection.journal_entry_id, collection.reference, collection.branch_id,
             collection.operation_id, collection.created_at),
        )

    def get(self, collection_id: str) -> Collection | None:
        row = self._query_one(f"SELECT {_COLUMNS} FROM collections WHERE id=?", (collection_id,))
        return _to_entity(row) if row else None

    def find_by_operation_id(self, operation_id: str) -> Collection | None:
        row = self._query_one(
            f"SELECT {_COLUMNS} FROM collections WHERE operation_id=?", (operation_id,)
        )
        return _to_entity(row) if row else None

    def list_by_receivable(self, receivable_id: str) -> list[Collection]:
        rows = self._query(
            f"SELECT {_COLUMNS} FROM collections WHERE receivable_id=? ORDER BY collection_date",
            (receivable_id,),
        )
        return [_to_entity(row) for row in rows]
