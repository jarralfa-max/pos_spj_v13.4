"""Journal repository — journals and gap-free entry numbering."""

from __future__ import annotations

from backend.domain.finance.entities.journal import Journal
from backend.domain.finance.enums import JournalType
from backend.infrastructure.db.repositories.finance.base import FinanceRepositoryBase

_COLUMNS = "id, journal_type, name, entry_sequence_prefix, active, created_at"


def _to_entity(row: dict) -> Journal:
    return Journal(
        id=row["id"],
        journal_type=JournalType(row["journal_type"]),
        name=row["name"],
        entry_sequence_prefix=row["entry_sequence_prefix"],
        active=bool(row["active"]),
        created_at=row["created_at"],
    )


class JournalRepository(FinanceRepositoryBase):
    def save(self, journal: Journal) -> None:
        self._execute(
            "INSERT INTO journals (id, journal_type, name, entry_sequence_prefix, active, created_at)"
            " VALUES (?,?,?,?,?,?)",
            (journal.id, journal.journal_type.value, journal.name,
             journal.entry_sequence_prefix, int(journal.active), journal.created_at),
        )

    def get(self, journal_id: str) -> Journal | None:
        row = self._query_one(f"SELECT {_COLUMNS} FROM journals WHERE id=?", (journal_id,))
        return _to_entity(row) if row else None

    def get_by_type(self, journal_type: JournalType) -> Journal | None:
        row = self._query_one(
            f"SELECT {_COLUMNS} FROM journals WHERE journal_type=?", (journal_type.value,)
        )
        return _to_entity(row) if row else None

    def list_all(self) -> list[Journal]:
        return [_to_entity(row) for row in self._query(f"SELECT {_COLUMNS} FROM journals ORDER BY name")]

    def next_entry_number(self, journal: Journal) -> str:
        """Atomically consume the journal sequence (UPDATE inside the UoW transaction)."""
        self._execute(
            "UPDATE journals SET next_sequence = next_sequence + 1 WHERE id=?", (journal.id,)
        )
        row = self._query_one("SELECT next_sequence FROM journals WHERE id=?", (journal.id,))
        sequence = int(row["next_sequence"]) - 1
        return f"{journal.entry_sequence_prefix}-{sequence:06d}"
