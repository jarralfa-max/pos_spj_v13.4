"""Journal entity — a book grouping entries by business source."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

from backend.domain.finance.enums import JournalType
from backend.domain.finance.exceptions import FinanceDomainError
from backend.shared.ids import new_uuid


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass(slots=True)
class Journal:
    id: str
    journal_type: JournalType
    name: str
    entry_sequence_prefix: str
    active: bool = True
    created_at: str = field(default_factory=_utcnow)

    @classmethod
    def create(cls, journal_type: JournalType, name: str, entry_sequence_prefix: str | None = None) -> "Journal":
        if not name or not name.strip():
            raise FinanceDomainError("Journal.name is required")
        return cls(
            id=new_uuid(),
            journal_type=journal_type,
            name=name.strip(),
            entry_sequence_prefix=(entry_sequence_prefix or journal_type.value[:3]).upper(),
        )
