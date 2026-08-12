"""Warehouse / WarehouseZone / StorageLocation entities (§12).

Locations form a hierarchy (warehouse → zone → aisle → rack → level → position)
via ``parent_location_id``; the UI never hardcodes locations. All ids are UUIDv7.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal

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


def _check_capacity(capacity: Decimal | None) -> None:
    if capacity is None:
        return
    if isinstance(capacity, float):
        raise InventoryDomainError("La capacidad no admite float (usa Decimal)")
    if not isinstance(capacity, Decimal):
        raise InventoryDomainError("La capacidad debe ser Decimal")
    if capacity < 0:
        raise InventoryDomainError("La capacidad no puede ser negativa")


@dataclass(slots=True)
class Warehouse:
    id: str
    code: str
    name: str
    branch_id: str
    warehouse_type: WarehouseType
    status: WarehouseStatus = WarehouseStatus.ACTIVE
    temperature_profile: str | None = None
    capacity: Decimal | None = None
    capacity_uom: str | None = None
    allow_sales_allocation: bool = True
    allow_purchase_receipt: bool = True
    allow_production: bool = False
    allow_quarantine: bool = False
    created_at: str = field(default_factory=_utcnow)
    updated_at: str = field(default_factory=_utcnow)

    def __post_init__(self) -> None:
        _check_capacity(self.capacity)

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

    def deactivate(self) -> None:
        self.status = WarehouseStatus.INACTIVE
        self.updated_at = _utcnow()

    def update_details(self, *, name: str | None = None,
                       warehouse_type: WarehouseType | None = None,
                       temperature_profile: str | None = ...,
                       capacity: Decimal | None = ...,
                       capacity_uom: str | None = ...,
                       allow_sales_allocation: bool | None = None,
                       allow_purchase_receipt: bool | None = None,
                       allow_production: bool | None = None,
                       allow_quarantine: bool | None = None) -> None:
        """Edit mutable warehouse details (§24 "Editar almacén"). ``...`` means
        "leave unchanged" for the optional/nullable fields so callers can clear
        them explicitly with ``None`` without every field being mandatory."""
        if name is not None:
            if not name.strip():
                raise InventoryDomainError("El almacén requiere nombre")
            self.name = name
        if warehouse_type is not None:
            self.warehouse_type = warehouse_type
        if temperature_profile is not ...:
            self.temperature_profile = temperature_profile
        if capacity is not ...:
            _check_capacity(capacity)
            self.capacity = capacity
        if capacity_uom is not ...:
            self.capacity_uom = capacity_uom
        if allow_sales_allocation is not None:
            self.allow_sales_allocation = allow_sales_allocation
        if allow_purchase_receipt is not None:
            self.allow_purchase_receipt = allow_purchase_receipt
        if allow_production is not None:
            self.allow_production = allow_production
        if allow_quarantine is not None:
            self.allow_quarantine = allow_quarantine
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
    capacity: Decimal | None = None

    def __post_init__(self) -> None:
        _check_capacity(self.capacity)

    @classmethod
    def create(cls, *, warehouse_id: str, code: str, name: str,
               zone_id: str | None = None, parent_location_id: str | None = None,
               level: int = 0, capacity: Decimal | None = None) -> "StorageLocation":
        if not warehouse_id:
            raise InventoryDomainError("La ubicación requiere almacén")
        if not code or not name:
            raise InventoryDomainError("La ubicación requiere código y nombre")
        if level < 0:
            raise InventoryDomainError("El nivel de jerarquía no puede ser negativo")
        return cls(id=new_uuid(), warehouse_id=warehouse_id, code=code, name=name,
                   zone_id=zone_id, parent_location_id=parent_location_id, level=level,
                   capacity=capacity)

    @property
    def is_active(self) -> bool:
        return self.status is LocationStatus.ACTIVE

    def block(self) -> None:
        self.status = LocationStatus.BLOCKED

    def activate(self) -> None:
        self.status = LocationStatus.ACTIVE

    def deactivate(self) -> None:
        self.status = LocationStatus.INACTIVE

    def update_details(self, *, name: str | None = None,
                       capacity: Decimal | None = ...) -> None:
        """Edit mutable location details (§24 "Editar ubicación")."""
        if name is not None:
            if not name.strip():
                raise InventoryDomainError("La ubicación requiere nombre")
            self.name = name
        if capacity is not ...:
            _check_capacity(capacity)
            self.capacity = capacity
