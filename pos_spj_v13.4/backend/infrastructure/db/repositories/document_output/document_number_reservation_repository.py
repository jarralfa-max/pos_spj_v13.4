"""SqliteDocumentNumberReservationRepository — persists the idempotency
ledger backing SET-16 "Idempotencia": one row per successful reservation,
keyed UNIQUE(sequence_id, operation_id). Implements
`backend.domain.document_output.repository_ports.DocumentNumberReservationRepositoryPort`.

A caller (a future application-layer use case) is expected to call
`get_by_operation_id()` first, pass whatever it finds as
`existing_reservation` to
`policies/sequence_reservation_policy.py::reserve_with_idempotency`, and
only call `save()` when that policy actually advanced the sequence — this
repository does not enforce that ordering itself, the same division
`SqlitePrintJobRepository`/`SqliteConfigurationValueRepository` already
have between "the entity decides", "the policy coordinates", and "the
repository persists".
"""

from __future__ import annotations

from datetime import datetime, timezone

from backend.domain.document_output.value_objects.document_number import DocumentNumber
from backend.infrastructure.db.repositories.document_output.base import DocumentOutputRepositoryBase
from backend.shared.ids import new_uuid

_COLS = (
    "id, sequence_id, operation_id, prefix, period_key, sequence_value, document_number, reserved_at"
)


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class SqliteDocumentNumberReservationRepository(DocumentOutputRepositoryBase):
    def save(self, sequence_id: str, operation_id: str, document_number: DocumentNumber) -> None:
        self._execute(
            f"INSERT INTO document_number_reservations ({_COLS}) VALUES (?,?,?,?,?,?,?,?)",
            (
                new_uuid(), sequence_id, operation_id, document_number.prefix, document_number.period_key,
                document_number.sequence_value, document_number.formatted(), _utcnow(),
            ),
        )

    def get_by_operation_id(self, sequence_id: str, operation_id: str) -> DocumentNumber | None:
        row = self._query_one(
            f"SELECT {_COLS} FROM document_number_reservations WHERE sequence_id=? AND operation_id=?",
            (sequence_id, operation_id),
        )
        if row is None:
            return None
        return DocumentNumber.create(
            prefix=row["prefix"], period_key=row["period_key"], sequence_value=row["sequence_value"],
        )
