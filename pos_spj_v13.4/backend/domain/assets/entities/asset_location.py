"""AssetLocation — hierarchical physical location (§18).

Empresa → Sucursal → Área → Cuarto → Posición. Never a free-text location
string (that's exactly the legacy `ubicacion = "Bodega"` pattern §18/§109
forbids).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

from backend.domain.assets.enums import AssetLocationStatus, AssetLocationType
from backend.domain.assets.exceptions import AssetDomainError
from backend.shared.ids import new_uuid


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass(slots=True)
class AssetLocation:
    id: str
    branch_id: str
    code: str
    name: str
    location_type: AssetLocationType
    parent_location_id: str | None = None
    status: AssetLocationStatus = AssetLocationStatus.ACTIVE
    created_at: str = field(default_factory=_utcnow)
    updated_at: str = field(default_factory=_utcnow)

    @classmethod
    def create(cls, branch_id: str, code: str, name: str,
               location_type: AssetLocationType, *,
               parent_location_id: str | None = None) -> "AssetLocation":
        if not branch_id:
            raise AssetDomainError("AssetLocation.branch_id is required")
        if not code or not code.strip():
            raise AssetDomainError("AssetLocation.code is required")
        if not name or not name.strip():
            raise AssetDomainError("AssetLocation.name is required")
        if location_type is not AssetLocationType.BRANCH and parent_location_id is None:
            raise AssetDomainError(
                "AssetLocation below BRANCH level requires a parent_location_id")
        return cls(
            id=new_uuid(), branch_id=branch_id, code=code.strip().upper(),
            name=name.strip(), location_type=location_type,
            parent_location_id=parent_location_id,
        )

    def deactivate(self) -> None:
        self.status = AssetLocationStatus.INACTIVE
        self.updated_at = _utcnow()

    def reactivate(self) -> None:
        self.status = AssetLocationStatus.ACTIVE
        self.updated_at = _utcnow()

    def is_active(self) -> bool:
        return self.status is AssetLocationStatus.ACTIVE
