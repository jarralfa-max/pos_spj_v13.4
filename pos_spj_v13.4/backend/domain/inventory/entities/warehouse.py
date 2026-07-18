"""Warehouse / WarehouseZone / StorageLocation entities (§12).

Locations form a hierarchy (warehouse → zone → aisle → rack → level → position)
via ``parent_location_id``; the UI never hardcodes locations. All ids are UUIDv7.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

from backend.domain.inventory.enums import (
    LocationStatus,
    WarehouseStatus,
    WarehouseType,
    WarehouseZoneType,
)
from backend.domain.inventory.exceptions import InventoryDomainError
from backend.shared.ids import new_uuid


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass(slots=True)
class Warehouse:
    id: str
    code: str
    name: str
    branch_id: str
    warehouse_type: WarehouseType
    status: WarehouseStatus = WarehouseStatus.ACTIVE
    temperature_profile: str | None = None
    allow_sales_allocation: bool = True
    allow_purchase_receipt: bool = True
    allow_production: bool = False
    allow_quarantine: bool = False
    created_at: str = field(default_factory=_utcnow)
    updated_at: str = field(default_factory=_utcnow)

    @classmethod
    def create(cls, *, code: str, name: str, branch_id: str,
               warehouse_type: WarehouseType, **kwargs) -> "Warehouse":
        if not code or not name:
            raise InventoryDomainError("El almacén requiere código y nombre")
        if not branch_id:
            raise InventoryDomainError("El almacén requiere sucursal")
        return cls(id=new_uuid(), code=code, name=name, branch_id=branch_id,
                   warehouse_type=warehouse_type, **kwargs)

    @property
    def is_active(self) -> bool:
        return self.status is WarehouseStatus.ACTIVE

    def block(self) -> None:
        self.status = WarehouseStatus.BLOCKED
        self.updated_at = _utcnow()

    def activate(self) -> None:
        self.status = WarehouseStatus.ACTIVE
        self.updated_at = _utcnow()


@dataclass(slots=True)
class WarehouseZone:
    id: str
    warehouse_id: str
    code: str
    name: str
    zone_type: WarehouseZoneType

    @classmethod
    def create(cls, *, warehouse_id: str, code: str, name: str,
               zone_type: WarehouseZoneType) -> "WarehouseZone":
        if not warehouse_id:
            raise InventoryDomainError("La zona requiere almacén")
        if not code or not name:
            raise InventoryDomainError("La zona requiere código y nombre")
        return cls(id=new_uuid(), warehouse_id=warehouse_id, code=code,
                   name=name, zone_type=zone_type)


@dataclass(slots=True)
class StorageLocation:
    id: str
    warehouse_id: str
    code: str
    name: str
    zone_id: str | None = None
    parent_location_id: str | None = None
    level: int = 0
    status: LocationStatus = LocationStatus.ACTIVE

    @classmethod
    def create(cls, *, warehouse_id: str, code: str, name: str,
               zone_id: str | None = None, parent_location_id: str | None = None,
               level: int = 0) -> "StorageLocation":
        if not warehouse_id:
            raise InventoryDomainError("La ubicación requiere almacén")
        if not code or not name:
            raise InventoryDomainError("La ubicación requiere código y nombre")
        if level < 0:
            raise InventoryDomainError("El nivel de jerarquía no puede ser negativo")
        return cls(id=new_uuid(), warehouse_id=warehouse_id, code=code, name=name,
                   zone_id=zone_id, parent_location_id=parent_location_id, level=level)

    @property
    def is_active(self) -> bool:
        return self.status is LocationStatus.ACTIVE

    def block(self) -> None:
        self.status = LocationStatus.BLOCKED
