"""ProductionArea (§19). Top of the resource hierarchy: área → centro de
trabajo → estación → equipo. Master data only — no state machine, just
active/inactive so a decommissioned area stops being offered for new orders
without losing its history."""

from dataclasses import dataclass, field
from datetime import datetime, timezone

from backend.domain.meat_processing.entities._validation import required_uuid
from backend.domain.meat_processing.exceptions import MeatProcessingInvariantError


@dataclass
class ProductionArea:
    id: str
    branch_id: str
    warehouse_id: str
    code: str
    name: str
    is_active: bool = True
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def __post_init__(self) -> None:
        for name in ("id", "branch_id", "warehouse_id"):
            setattr(self, name, required_uuid(getattr(self, name), name))
        if not str(self.code or "").strip():
            raise MeatProcessingInvariantError("code es requerido")
        if not str(self.name or "").strip():
            raise MeatProcessingInvariantError("name es requerido")

    def deactivate(self) -> None:
        self.is_active = False

    def activate(self) -> None:
        self.is_active = True
