"""SqliteDocumentNumberSequenceRepository — persists `DocumentNumberSequence`
(SET-16). Implements
`backend.domain.document_output.repository_ports.DocumentNumberSequenceRepositoryPort`.
"""

from __future__ import annotations

from datetime import datetime, timezone

from backend.domain.document_output.entities.document_number_sequence import DocumentNumberSequence
from backend.domain.document_output.enums import SequenceResetPolicy
from backend.infrastructure.db.repositories.document_output.base import DocumentOutputRepositoryBase

_COLS = "id, prefix, reset_policy, period_key, current_value, created_at, updated_at"


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class SqliteDocumentNumberSequenceRepository(DocumentOutputRepositoryBase):
    def save(self, sequence: DocumentNumberSequence) -> None:
        self._execute(
            f"INSERT INTO document_number_sequences ({_COLS})"
            " VALUES (?,?,?,?,?,?,?)"
            " ON CONFLICT(id) DO UPDATE SET"
            " period_key=excluded.period_key, current_value=excluded.current_value,"
            " updated_at=excluded.updated_at",
            self._params(sequence),
        )

    def get(self, sequence_id: str) -> DocumentNumberSequence | None:
        row = self._query_one(f"SELECT {_COLS} FROM document_number_sequences WHERE id=?", (sequence_id,))
        return self._hydrate(row) if row else None

    def get_by_prefix(self, prefix: str) -> DocumentNumberSequence | None:
        row = self._query_one(
            f"SELECT {_COLS} FROM document_number_sequences WHERE prefix=?", (prefix.strip().upper(),),
        )
        return self._hydrate(row) if row else None

    def reserve_and_get(self, sequence_id: str, *, period_key: str) -> int:
        """SET-16 cutover: atomically reserves the next value for
        `period_key` in ONE `UPDATE ... RETURNING` statement — both the
        common-case increment and the period-rollover reset happen in
        the same atomic write, so a concurrent rollover can never
        collide (whichever writer's UPDATE actually commits first
        evaluates the CASE against the row's true current state; a
        second, concurrent rollover attempt then correctly sees the
        already-rolled `period_key` and increments from 1, never lands
        on a colliding 1 itself). Never a Python read-modify-write —
        `save()` stays as the write path for admin operations
        (`force_reset`, direct upserts) where writing an explicit value
        is correct."""
        row = self._query_one(
            "UPDATE document_number_sequences"
            " SET current_value = CASE WHEN period_key = ? THEN current_value + 1 ELSE 1 END,"
            "     period_key = ?, updated_at = ?"
            " WHERE id = ?"
            " RETURNING current_value",
            (period_key, period_key, _utcnow(), sequence_id),
        )
        return row["current_value"]

    # helpers -----------------------------------------------------------------
    @staticmethod
    def _params(sequence: DocumentNumberSequence) -> tuple:
        return (
            sequence.id, sequence.prefix, sequence.reset_policy.value, sequence.period_key,
            sequence.current_value, sequence.created_at, sequence.updated_at,
        )

    @staticmethod
    def _hydrate(row: dict) -> DocumentNumberSequence:
        return DocumentNumberSequence(
            id=row["id"], prefix=row["prefix"], reset_policy=SequenceResetPolicy(row["reset_policy"]),
            period_key=row["period_key"], current_value=row["current_value"], created_at=row["created_at"],
            updated_at=row["updated_at"],
        )
