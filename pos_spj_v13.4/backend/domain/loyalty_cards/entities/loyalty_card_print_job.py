"""LoyaltyCardPrintJob — tracks one render attempt of a batch (or one sheet
of it) to PDF (master prompt §50-51).

A first draft of LOY-22 tried to reuse `backend.domain.document_output.
entities.print_job.PrintJob` directly (a real, already-built, already-
tested generic print-job entity) rather than inventing a parallel one. That
entity's own docstring says `source_module`/`source_document_id` are
"opaque references... never resolved or validated against another bounded
context" — which reads as an invitation to also pass a foreign
`template_version_id`. It is NOT: `print_jobs.template_version_id` carries
a REAL, enforced `REFERENCES document_template_versions(id)` foreign key at
the SCHEMA level (confirmed by a real `sqlite3.OperationalError` under
`PRAGMA foreign_keys = ON`, not by reading the docstring) — reusing that
table would require also materializing a matching row in document_output's
OWN template-version table for every `LoyaltyCardTemplateVersion`, a much
larger and semantically wrong cross-context integration (their templates
are ESC_POS/HTML/PDF/ZPL text templates; ours are declarative visual card
designs). Lesson: an entity's docstring describing a field as "opaque"
describes the DOMAIN layer's own validation, not the persisted schema's
foreign keys — check the actual DDL before assuming a cross-context field
is a free passthrough.

This entity instead lives entirely in `loyalty_cards`' own schema, mirroring
`PrintJob`'s status-machine SHAPE for conceptual consistency (a future
convergence is possible once/if document_output's template model is
generalized) without any cross-schema FK risk.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

from backend.domain.loyalty_cards.enums import LoyaltyCardPrintJobStatus
from backend.domain.loyalty_cards.exceptions import (
    InvalidLoyaltyCardPrintJobError,
    InvalidLoyaltyCardPrintJobStateError,
)
from backend.shared.ids import new_uuid


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass(slots=True)
class LoyaltyCardPrintJob:
    id: str
    batch_id: str
    requested_by_user_id: str
    only_sheet_number: int | None = None
    status: LoyaltyCardPrintJobStatus = LoyaltyCardPrintJobStatus.PENDING
    failure_reason: str | None = None
    reprint_of_job_id: str | None = None
    reprint_reason: str | None = None
    requested_at: str = field(default_factory=_utcnow)
    rendered_at: str | None = None
    created_at: str = field(default_factory=_utcnow)
    updated_at: str = field(default_factory=_utcnow)

    def __post_init__(self) -> None:
        if not self.batch_id:
            raise InvalidLoyaltyCardPrintJobError("batch_id es obligatorio")
        if not self.requested_by_user_id:
            raise InvalidLoyaltyCardPrintJobError("requested_by_user_id es obligatorio")
        if self.only_sheet_number is not None and self.only_sheet_number <= 0:
            raise InvalidLoyaltyCardPrintJobError("only_sheet_number debe ser positivo")

    @classmethod
    def create(cls, batch_id: str, *, requested_by_user_id: str,
               only_sheet_number: int | None = None) -> "LoyaltyCardPrintJob":
        return cls(id=new_uuid(), batch_id=batch_id, requested_by_user_id=requested_by_user_id,
                   only_sheet_number=only_sheet_number)

    def create_reprint(self, *, requested_by_user_id: str,
                        reason: str) -> "LoyaltyCardPrintJob":
        """§50-51: a reprint is always a NEW job, never a mutation of this
        one, and always carries a reason."""
        if not (reason or "").strip():
            raise InvalidLoyaltyCardPrintJobError("La reimpresión requiere un motivo")
        return LoyaltyCardPrintJob(
            id=new_uuid(), batch_id=self.batch_id, requested_by_user_id=requested_by_user_id,
            only_sheet_number=self.only_sheet_number, reprint_of_job_id=self.id,
            reprint_reason=reason.strip())

    def start_rendering(self) -> None:
        if self.status is not LoyaltyCardPrintJobStatus.PENDING:
            raise InvalidLoyaltyCardPrintJobStateError(
                f"Solo se renderiza desde PENDING (actual: {self.status.value})")
        self.status = LoyaltyCardPrintJobStatus.RENDERING
        self.updated_at = _utcnow()

    def mark_ready(self) -> None:
        if self.status is not LoyaltyCardPrintJobStatus.RENDERING:
            raise InvalidLoyaltyCardPrintJobStateError(
                f"Solo se marca listo desde RENDERING (actual: {self.status.value})")
        self.status = LoyaltyCardPrintJobStatus.READY
        self.rendered_at = _utcnow()
        self.updated_at = _utcnow()

    def fail(self, reason: str) -> None:
        if self.status is not LoyaltyCardPrintJobStatus.RENDERING:
            raise InvalidLoyaltyCardPrintJobStateError(
                f"Solo se falla desde RENDERING (actual: {self.status.value})")
        if not (reason or "").strip():
            raise InvalidLoyaltyCardPrintJobError("fail() requiere un motivo")
        self.status = LoyaltyCardPrintJobStatus.FAILED
        self.failure_reason = reason.strip()
        self.updated_at = _utcnow()

    def cancel(self) -> None:
        if self.status not in (LoyaltyCardPrintJobStatus.PENDING,
                               LoyaltyCardPrintJobStatus.RENDERING):
            raise InvalidLoyaltyCardPrintJobStateError(
                f"No se puede cancelar desde {self.status.value}")
        self.status = LoyaltyCardPrintJobStatus.CANCELLED
        self.updated_at = _utcnow()
