"""ProductionEquipment (§19). `status` is the equipment's physical condition
(AVAILABLE/MAINTENANCE/RETIRED) — whether it is *currently assigned* to an
order is tracked separately by EquipmentAssignment, the same split
Losses/Inventory use between "item exists" and "item is in use right now"."""

from dataclasses import dataclass, field
from datetime import datetime, timezone

from backend.domain.meat_processing.entities._validation import optional_uuid, required_uuid
from backend.domain.meat_processing.enums import EquipmentStatus
from backend.domain.meat_processing.exceptions import (
    MeatProcessingInvariantError,
    MeatProcessingStateTransitionError,
)


@dataclass
class ProductionEquipment:
    id: str
    work_center_id: str
    code: str
    name: str
    equipment_type: str
    station_id: str | None = None
    status: EquipmentStatus = EquipmentStatus.AVAILABLE
    last_maintenance_at: datetime | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def __post_init__(self) -> None:
        for name in ("id", "work_center_id"):
            setattr(self, name, required_uuid(getattr(self, name), name))
        self.station_id = optional_uuid(self.station_id, "station_id")
        if not str(self.code or "").strip():
            raise MeatProcessingInvariantError("code es requerido")
        if not str(self.name or "").strip():
            raise MeatProcessingInvariantError("name es requerido")
        if not str(self.equipment_type or "").strip():
            raise MeatProcessingInvariantError("equipment_type es requerido")
        if not isinstance(self.status, EquipmentStatus):
            raise MeatProcessingInvariantError("status de equipo canónico requerido")

    @property
    def is_available(self) -> bool:
        return self.status is EquipmentStatus.AVAILABLE

    def start_maintenance(self) -> None:
        if self.status is not EquipmentStatus.AVAILABLE:
            raise MeatProcessingStateTransitionError(
                "Solo un equipo disponible puede entrar a mantenimiento")
        self.status = EquipmentStatus.MAINTENANCE

    def complete_maintenance(self, *, completed_at: datetime | None = None) -> None:
        if self.status is not EquipmentStatus.MAINTENANCE:
            raise MeatProcessingStateTransitionError(
                "El equipo no está en mantenimiento")
        self.status = EquipmentStatus.AVAILABLE
        self.last_maintenance_at = completed_at or datetime.now(timezone.utc)

    def retire(self) -> None:
        if self.status is EquipmentStatus.RETIRED:
            raise MeatProcessingStateTransitionError("El equipo ya está retirado")
        self.status = EquipmentStatus.RETIRED
