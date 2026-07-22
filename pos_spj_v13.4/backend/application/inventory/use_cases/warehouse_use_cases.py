"""Warehouse / zone / location management use cases (§12, INV-5).

CRUD + state transitions for the storage topology: warehouses, their zones and
the storage-location hierarchy (warehouse → zone → aisle → rack → level →
position via ``parent_location_id``). Every mutation re-validates its granular
permission, is idempotent by natural code, audits, and emits the canonical
warehouse/location event. Locations never move stock — that's the ledger's job.
"""

from __future__ import annotations

import json

from backend.application.inventory.authorization import InventoryAuthorizationPolicy
from backend.application.inventory.permissions import InventoryPermissions
from backend.application.inventory.result import InventoryResult
from backend.domain.inventory.entities.warehouse import (
    StorageLocation,
    Warehouse,
    WarehouseZone,
)
from backend.domain.inventory.enums import (
    LocationStatus,
    WarehouseStatus,
    WarehouseType,
    WarehouseZoneType,
)
from backend.domain.inventory.events import InventoryEvents, build_event_payload
from backend.domain.inventory.exceptions import (
    InventoryDomainError,
    InventoryPermissionDeniedError,
)
from backend.infrastructure.db.repositories.inventory.unit_of_work import (
    InventoryUnitOfWork,
)


def _emit(uow, event_name, *, entity_id, actor, **extra):
    payload = build_event_payload(event_name, operation_id=entity_id,
                                  entity_id=entity_id, user_id=actor, **extra)
    uow.outbox.enqueue(event_id=payload["event_id"], event_name=event_name,
                       payload_json=json.dumps(payload), operation_id=entity_id)


class CreateWarehouseUseCase:
    def __init__(self, authorization: InventoryAuthorizationPolicy | None = None) -> None:
        self._auth = authorization or InventoryAuthorizationPolicy()

    def execute(self, connection, *, code: str, name: str, branch_id: str,
                warehouse_type: WarehouseType, actor_user_id: str,
                **options) -> InventoryResult:
        try:
            self._auth.require(actor_user_id, InventoryPermissions.WAREHOUSE_CREATE)
        except InventoryPermissionDeniedError as exc:
            return InventoryResult.fail(str(exc), "PERMISSION_DENIED")
        try:
            with InventoryUnitOfWork(connection) as uow:
                existing = uow.warehouses.get_by_code(code)
                if existing is not None:
                    return InventoryResult.ok("Almacén ya existe (idempotente)",
                                              entity_id=existing["id"], idempotent=True)
                wh = Warehouse.create(code=code, name=name, branch_id=branch_id,
                                      warehouse_type=warehouse_type, **options)
                uow.warehouses.save_warehouse(wh)
                uow.audit.record(entity_type="WAREHOUSE", entity_id=wh.id,
                                 action="CREATED", user_id=actor_user_id,
                                 branch_id=branch_id)
                _emit(uow, InventoryEvents.WAREHOUSE_CREATED, entity_id=wh.id,
                      actor=actor_user_id, branch_id=branch_id)
        except InventoryDomainError as exc:
            return InventoryResult.fail(str(exc), "INVENTORY_RULE_VIOLATION")
        return InventoryResult.ok("Almacén creado", entity_id=wh.id)


class SetWarehouseStatusUseCase:
    def __init__(self, authorization: InventoryAuthorizationPolicy | None = None) -> None:
        self._auth = authorization or InventoryAuthorizationPolicy()

    def execute(self, connection, *, warehouse_id: str, activate: bool,
                actor_user_id: str, reason: str = "") -> InventoryResult:
        permission = (InventoryPermissions.WAREHOUSE_ACTIVATE if activate
                      else InventoryPermissions.WAREHOUSE_BLOCK)
        event = (InventoryEvents.WAREHOUSE_ACTIVATED if activate
                 else InventoryEvents.WAREHOUSE_BLOCKED)
        try:
            self._auth.require(actor_user_id, permission)
        except InventoryPermissionDeniedError as exc:
            return InventoryResult.fail(str(exc), "PERMISSION_DENIED")
        with InventoryUnitOfWork(connection) as uow:
            row = uow.warehouses.get_warehouse(warehouse_id)
            if row is None:
                return InventoryResult.fail("Almacén no encontrado", "NOT_FOUND")
            wh = _warehouse_from_row(row)
            wh.activate() if activate else wh.block()
            uow.warehouses.save_warehouse(wh)
            uow.audit.record(entity_type="WAREHOUSE", entity_id=wh.id,
                             action=wh.status.value, user_id=actor_user_id, reason=reason,
                             branch_id=wh.branch_id)
            _emit(uow, event, entity_id=wh.id, actor=actor_user_id, branch_id=wh.branch_id)
        return InventoryResult.ok(f"Almacén {wh.status.value}", entity_id=wh.id)


class CreateZoneUseCase:
    def __init__(self, authorization: InventoryAuthorizationPolicy | None = None) -> None:
        self._auth = authorization or InventoryAuthorizationPolicy()

    def execute(self, connection, *, warehouse_id: str, code: str, name: str,
                zone_type: WarehouseZoneType, actor_user_id: str) -> InventoryResult:
        try:
            self._auth.require(actor_user_id, InventoryPermissions.LOCATION_MANAGE)
        except InventoryPermissionDeniedError as exc:
            return InventoryResult.fail(str(exc), "PERMISSION_DENIED")
        try:
            with InventoryUnitOfWork(connection) as uow:
                for existing in uow.warehouses.list_zones(warehouse_id):
                    if existing["code"] == code:
                        return InventoryResult.ok("Zona ya existe (idempotente)",
                                                  entity_id=existing["id"], idempotent=True)
                zone = WarehouseZone.create(warehouse_id=warehouse_id, code=code,
                                            name=name, zone_type=zone_type)
                uow.warehouses.save_zone(zone)
                uow.audit.record(entity_type="WAREHOUSE_ZONE", entity_id=zone.id,
                                 action="CREATED", user_id=actor_user_id)
        except InventoryDomainError as exc:
            return InventoryResult.fail(str(exc), "INVENTORY_RULE_VIOLATION")
        return InventoryResult.ok("Zona creada", entity_id=zone.id)


class CreateLocationUseCase:
    def __init__(self, authorization: InventoryAuthorizationPolicy | None = None) -> None:
        self._auth = authorization or InventoryAuthorizationPolicy()

    def execute(self, connection, *, warehouse_id: str, code: str, name: str,
                actor_user_id: str, zone_id: str | None = None,
                parent_location_id: str | None = None, level: int = 0) -> InventoryResult:
        try:
            self._auth.require(actor_user_id, InventoryPermissions.LOCATION_MANAGE)
        except InventoryPermissionDeniedError as exc:
            return InventoryResult.fail(str(exc), "PERMISSION_DENIED")
        try:
            with InventoryUnitOfWork(connection) as uow:
                for existing in uow.warehouses.list_locations(warehouse_id):
                    if existing["code"] == code:
                        return InventoryResult.ok("Ubicación ya existe (idempotente)",
                                                  entity_id=existing["id"], idempotent=True)
                if parent_location_id and uow.warehouses.get_location(parent_location_id) is None:
                    return InventoryResult.fail("Ubicación padre no encontrada", "NOT_FOUND")
                loc = StorageLocation.create(
                    warehouse_id=warehouse_id, code=code, name=name, zone_id=zone_id,
                    parent_location_id=parent_location_id, level=level)
                uow.warehouses.save_location(loc)
                uow.audit.record(entity_type="STORAGE_LOCATION", entity_id=loc.id,
                                 action="CREATED", user_id=actor_user_id)
                _emit(uow, InventoryEvents.LOCATION_CREATED, entity_id=loc.id,
                      actor=actor_user_id)
        except InventoryDomainError as exc:
            return InventoryResult.fail(str(exc), "INVENTORY_RULE_VIOLATION")
        return InventoryResult.ok("Ubicación creada", entity_id=loc.id)


class SetLocationStatusUseCase:
    def __init__(self, authorization: InventoryAuthorizationPolicy | None = None) -> None:
        self._auth = authorization or InventoryAuthorizationPolicy()

    def execute(self, connection, *, location_id: str, activate: bool,
                actor_user_id: str, reason: str = "") -> InventoryResult:
        try:
            self._auth.require(actor_user_id, InventoryPermissions.LOCATION_MANAGE)
        except InventoryPermissionDeniedError as exc:
            return InventoryResult.fail(str(exc), "PERMISSION_DENIED")
        with InventoryUnitOfWork(connection) as uow:
            row = uow.warehouses.get_location(location_id)
            if row is None:
                return InventoryResult.fail("Ubicación no encontrada", "NOT_FOUND")
            loc = _location_from_row(row)
            if activate:
                loc.status = LocationStatus.ACTIVE
            else:
                loc.block()
            uow.warehouses.save_location(loc)
            uow.audit.record(entity_type="STORAGE_LOCATION", entity_id=loc.id,
                             action=loc.status.value, user_id=actor_user_id, reason=reason)
            if not activate:
                _emit(uow, InventoryEvents.LOCATION_BLOCKED, entity_id=loc.id,
                      actor=actor_user_id)
        return InventoryResult.ok(f"Ubicación {loc.status.value}", entity_id=loc.id)


# ── row → entity helpers ────────────────────────────────────────────────────
def _warehouse_from_row(row: dict) -> Warehouse:
    return Warehouse(
        id=row["id"], code=row["code"], name=row["name"], branch_id=row["branch_id"],
        warehouse_type=WarehouseType(row["warehouse_type"]),
        status=WarehouseStatus(row["status"]),
        temperature_profile=row["temperature_profile"],
        allow_sales_allocation=bool(row["allow_sales_allocation"]),
        allow_purchase_receipt=bool(row["allow_purchase_receipt"]),
        allow_production=bool(row["allow_production"]),
        allow_quarantine=bool(row["allow_quarantine"]),
        created_at=row["created_at"], updated_at=row["updated_at"])


def _location_from_row(row: dict) -> StorageLocation:
    return StorageLocation(
        id=row["id"], warehouse_id=row["warehouse_id"], code=row["code"],
        name=row["name"], zone_id=row["zone_id"],
        parent_location_id=row["parent_location_id"], level=row["level"],
        status=LocationStatus(row["status"]))
