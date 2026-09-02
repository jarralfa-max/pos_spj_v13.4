"""DocumentNumber — SET-16 "Sequences": the formatted human-readable
folio (`PREFIX-PERIOD-NNNNNN`) a `DocumentNumberSequence` reservation
produces. Mirrors the shape `backend/domain/procurement/value_objects.py::
DocumentNumber` and `backend/domain/finance/value_objects/document_number.py::
DocumentNumber` already have in their own bounded contexts — same naming,
duplicated on purpose rather than imported (bounded-context independence,
the same discipline `DeviceStatus`/`WorkstationStatus` established). The
UUIDv7 `id` on `PrintJob`/`DocumentTemplate` etc. is always the real
identity; this is a readable reference, never a primary key.
"""

from __future__ import annotations

from dataclasses import dataclass

from backend.domain.document_output.exceptions import DocumentInvalidValueError


@dataclass(frozen=True, slots=True)
class DocumentNumber:
    prefix: str
    period_key: str
    sequence_value: int

    @classmethod
    def create(cls, *, prefix: str, period_key: str, sequence_value: int) -> "DocumentNumber":
        if not prefix.strip():
            raise DocumentInvalidValueError("prefix es obligatorio")
        if isinstance(sequence_value, bool) or not isinstance(sequence_value, int) or sequence_value < 1:
            raise DocumentInvalidValueError(
                f"sequence_value debe ser un entero >= 1, recibido {sequence_value!r}"
            )
        return cls(prefix=prefix.strip(), period_key=period_key, sequence_value=sequence_value)

    def formatted(self) -> str:
        if self.period_key:
            return f"{self.prefix}-{self.period_key}-{self.sequence_value:06d}"
        return f"{self.prefix}-{self.sequence_value:06d}"

    def __str__(self) -> str:
        return self.formatted()
