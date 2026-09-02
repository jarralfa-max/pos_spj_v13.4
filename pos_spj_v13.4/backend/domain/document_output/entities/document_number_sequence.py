"""DocumentNumberSequence — SET-16 "Sequences"/"Reservas"/"Reset": a
safe, explicit, per-prefix folio counter. Generalizes the ad-hoc
MAX(document_number)+1 scan
`backend/infrastructure/db/repositories/procurement/support_repositories.py::
DocumentSequenceRepository.next_number()` performs against a live
document table (a real race window: two concurrent reservations can read
the same MAX before either commits, and the only thing stopping a
collision is a UNIQUE constraint failing one of them after the fact) into
a persisted counter that increments in place. This is the
`DocumentNumberSequence` concept `migrations/MIGRATION_LOG.md`'s SET-10
entry already flagged as a future risk ("Folio duplicado al introducir
DocumentNumberSequence mientras next_number() legacy sigue activo") — see
that SET-16 entry for why Procurement's own generator isn't cut over in
this SET.

`reserve_next()` is the mechanical operation (always returns the next
value — no idempotency of its own, same "entity is permissive, a policy
enforces the stricter business rule on top" split `reprint_policy.py`
established in SET-12). `policies/sequence_reservation_policy.py::
reserve_with_idempotency` is where "Idempotencia" is actually enforced.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

from backend.domain.document_output.enums import SequenceResetPolicy
from backend.domain.document_output.exceptions import DocumentInvalidValueError
from backend.domain.document_output.value_objects.document_number import DocumentNumber
from backend.shared.ids import new_uuid


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _period_key_for(reset_policy: SequenceResetPolicy, at: datetime) -> str:
    if reset_policy is SequenceResetPolicy.NEVER:
        return ""
    if reset_policy is SequenceResetPolicy.YEARLY:
        return f"{at.year:04d}"
    if reset_policy is SequenceResetPolicy.MONTHLY:
        return f"{at.year:04d}-{at.month:02d}"
    return f"{at.year:04d}-{at.month:02d}-{at.day:02d}"  # DAILY


@dataclass(slots=True)
class DocumentNumberSequence:
    id: str
    prefix: str
    reset_policy: SequenceResetPolicy
    period_key: str = ""
    current_value: int = 0
    created_at: str = field(default_factory=_utcnow)
    updated_at: str = field(default_factory=_utcnow)

    @classmethod
    def create(
        cls, *, prefix: str, reset_policy: SequenceResetPolicy = SequenceResetPolicy.NEVER,
    ) -> "DocumentNumberSequence":
        if not prefix.strip():
            raise DocumentInvalidValueError("prefix es obligatorio")
        return cls(id=new_uuid(), prefix=prefix.strip().upper(), reset_policy=reset_policy)

    def _touch(self) -> None:
        self.updated_at = _utcnow()

    def reserve_next(self, *, at: datetime | None = None) -> DocumentNumber:
        """Always advances the counter by exactly one and returns the
        resulting `DocumentNumber` — automatically rolls the period (and
        resets `current_value` to 0 first) when the current moment falls
        in a different period than `period_key`, per `reset_policy`."""
        moment = at or datetime.now(timezone.utc)
        current_period = _period_key_for(self.reset_policy, moment)
        if self.reset_policy is not SequenceResetPolicy.NEVER and current_period != self.period_key:
            self.period_key = current_period
            self.current_value = 0
        self.current_value += 1
        self._touch()
        return DocumentNumber.create(
            prefix=self.prefix, period_key=self.period_key, sequence_value=self.current_value,
        )

    def force_reset(self, *, period_key: str = "") -> None:
        """Administrative override — resets the counter to 0 regardless
        of whether the period actually changed (e.g. correcting an
        operator mistake, or starting a new fiscal year manually).
        Distinct from `reserve_next()`'s automatic period rollover."""
        self.period_key = period_key
        self.current_value = 0
        self._touch()
