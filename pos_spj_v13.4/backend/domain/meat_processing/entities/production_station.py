"""ProductionStation (§19). A WorkCenter subdivided into individual
stations/lines — the level equipment (§19) actually attaches to."""

from dataclasses import dataclass, field
from datetime import datetime, timezone

from backend.domain.meat_processing.entities._validation import required_uuid
from backend.domain.meat_processing.exceptions import MeatProcessingInvariantError


@dataclass
class ProductionStation:
    id: str
    work_center_id: str
    code: str
    name: str
    is_active: bool = True
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def __post_init__(self) -> None:
        for name in ("id", "work_center_id"):
            setattr(self, name, required_uuid(getattr(self, name), name))
        if not str(self.code or "").strip():
            raise MeatProcessingInvariantError("code es requerido")
        if not str(self.name or "").strip():
            raise MeatProcessingInvariantError("name es requerido")

    def deactivate(self) -> None:
        self.is_active = False

    def activate(self) -> None:
        self.is_active = True
