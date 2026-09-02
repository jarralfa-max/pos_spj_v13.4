"""SequenceReservationPolicy — SET-16 "Idempotencia": reserving a
document number for the same `operation_id` twice must return the exact
same `DocumentNumber`, never advance the counter a second time — the
same discipline `configuration_values.operation_id` (Settings, SET-3) and
`print_jobs.operation_id` (Document Output, SET-11) already established
at the persistence layer. This function is the pure domain half of that:
the repository layer looks up any existing reservation for the
(sequence, operation_id) pair and passes it in here — this function never
touches a database itself.
"""

from __future__ import annotations

from backend.domain.document_output.entities.document_number_sequence import DocumentNumberSequence
from backend.domain.document_output.value_objects.document_number import DocumentNumber


def reserve_with_idempotency(
    sequence: DocumentNumberSequence, *, existing_reservation: DocumentNumber | None = None,
) -> DocumentNumber:
    if existing_reservation is not None:
        return existing_reservation
    return sequence.reserve_next()
