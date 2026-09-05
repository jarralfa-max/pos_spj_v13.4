"""ProductionLabel entity (§25). "La impresión no determina el éxito
productivo" — printing is tracked as a side artifact of a PackagingExecution,
never gates it. `mark_printed()` is idempotent-friendly: the first call
records the print; every call after that is a reprint.
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone

from backend.domain.meat_processing.entities._validation import required_uuid
from backend.domain.meat_processing.exceptions import MeatProcessingInvariantError


@dataclass
class ProductionLabel:
    id: str
    operation_id: str
    packaging_execution_id: str
    label_template_id: str
    barcode: str
    qr_traceability_reference: str
    printed_at: datetime | None = None
    printed_by_user_id: str | None = None
    reprint_count: int = 0
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def __post_init__(self) -> None:
        for name in ("id", "operation_id", "packaging_execution_id", "label_template_id"):
            setattr(self, name, required_uuid(getattr(self, name), name))
        if self.printed_by_user_id is not None:
            self.printed_by_user_id = required_uuid(
                self.printed_by_user_id, "printed_by_user_id")
        if self.id == self.operation_id:
            raise MeatProcessingInvariantError("entity_id y operation_id deben ser distintos")
        if not str(self.barcode or "").strip():
            raise MeatProcessingInvariantError("barcode es requerido")
        if not str(self.qr_traceability_reference or "").strip():
            raise MeatProcessingInvariantError("qr_traceability_reference es requerido")
        if self.reprint_count < 0:
            raise MeatProcessingInvariantError("reprint_count no puede ser negativo")

    @property
    def is_printed(self) -> bool:
        return self.printed_at is not None

    def mark_printed(self, *, actor_user_id: str, printed_at: datetime | None = None) -> None:
        actor = required_uuid(actor_user_id, "printed_by_user_id")
        moment = printed_at or datetime.now(timezone.utc)
        if self.printed_at is None:
            self.printed_at = moment
        else:
            self.reprint_count += 1
        self.printed_by_user_id = actor
