"""CustomerImportBatch — one run of ImportCustomersUseCase (§47). "Registra
creados/actualizados/rechazados/duplicados/errores" — this entity is that
running tally plus the batch's own approval lifecycle for sensitive
imports (§73: "quien importa no aprueba una importación sensible").

Status transitions:

    (is_sensitive=False) ──► PROCESSING ──finalize()──► COMPLETED/PARTIAL/FAILED
    (is_sensitive=True)  ──► PENDING_APPROVAL ──approve()──► PROCESSING ──finalize()──► ...
                                   │
                                   └──reject()──► REJECTED

Row-level detail is not modeled as a rich child *entity* here (unlike
Products' ProductImportBatch, which pairs with staged import rows) — this
aggregate only tracks counts. For a non-sensitive batch, rows are fully
transient: validated/matched/written or rejected within one
``ImportCustomersUseCase`` call, never touching disk on their own. A
*sensitive* batch (``is_sensitive=True``) is the one exception: it must
survive until a second, distinct approver calls
``ApproveCustomerImportUseCase`` — possibly a different session entirely —
so the submitted rows are round-tripped as a raw JSON blob at the
repository layer (``CustomerImportBatchRepository.save_pending_rows``/
``get_pending_rows``), the same "blob the domain entity doesn't need to
model" treatment this codebase already gives outbox event payloads. This
entity's own fields stay limited to what its lifecycle methods actually
reason about.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

from backend.domain.customers.enums import ImportBatchStatus
from backend.domain.customers.exceptions import InvalidCustomerImportError
from backend.shared.ids import new_uuid


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass(slots=True)
class CustomerImportBatch:
    id: str
    submitted_by_user_id: str
    is_sensitive: bool = False
    total_rows: int = 0
    created_count: int = 0
    updated_count: int = 0
    rejected_count: int = 0
    duplicate_count: int = 0
    error_count: int = 0
    status: ImportBatchStatus = ImportBatchStatus.PROCESSING
    approved_by_user_id: str | None = None
    approved_at: str | None = None
    operation_id: str | None = None
    created_at: str = field(default_factory=_utcnow)
    updated_at: str = field(default_factory=_utcnow)

    def _touch(self) -> None:
        self.updated_at = _utcnow()

    @classmethod
    def start(
        cls, submitted_by_user_id: str, total_rows: int, *, is_sensitive: bool = False,
        operation_id: str | None = None,
    ) -> "CustomerImportBatch":
        if not submitted_by_user_id:
            raise InvalidCustomerImportError("submitted_by_user_id es obligatorio")
        if total_rows <= 0:
            raise InvalidCustomerImportError("El lote de importación no tiene filas")
        return cls(
            id=new_uuid(), submitted_by_user_id=submitted_by_user_id, total_rows=total_rows,
            is_sensitive=is_sensitive,
            status=(ImportBatchStatus.PENDING_APPROVAL if is_sensitive
                   else ImportBatchStatus.PROCESSING),
            operation_id=operation_id,
        )

    def approve(self, approved_by_user_id: str) -> None:
        if self.status is not ImportBatchStatus.PENDING_APPROVAL:
            raise InvalidCustomerImportError(
                f"No se puede aprobar desde {self.status.value}")
        self.status = ImportBatchStatus.PROCESSING
        self.approved_by_user_id = approved_by_user_id
        self.approved_at = _utcnow()
        self._touch()

    def reject(self) -> None:
        if self.status is not ImportBatchStatus.PENDING_APPROVAL:
            raise InvalidCustomerImportError(
                f"No se puede rechazar desde {self.status.value}")
        self.status = ImportBatchStatus.REJECTED
        self._touch()

    def record_row(self, outcome: str) -> None:
        """outcome: one of CREATED/UPDATED/REJECTED/DUPLICATE/ERROR."""
        if outcome == "CREATED":
            self.created_count += 1
        elif outcome == "UPDATED":
            self.updated_count += 1
        elif outcome == "REJECTED":
            self.rejected_count += 1
        elif outcome == "DUPLICATE":
            self.duplicate_count += 1
        elif outcome == "ERROR":
            self.error_count += 1
        else:
            raise InvalidCustomerImportError(f"outcome desconocido: {outcome}")
        self._touch()

    def finalize(self) -> None:
        if self.status is not ImportBatchStatus.PROCESSING:
            raise InvalidCustomerImportError(
                f"No se puede finalizar desde {self.status.value}")
        written = self.created_count + self.updated_count
        if self.error_count and written:
            self.status = ImportBatchStatus.PARTIAL
        elif self.error_count and not written:
            self.status = ImportBatchStatus.FAILED
        else:
            self.status = ImportBatchStatus.COMPLETED
        self._touch()
