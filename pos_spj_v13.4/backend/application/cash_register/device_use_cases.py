"""CASH-6 device lifecycle use cases with authorization, audit and outbox."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from backend.application.cash_register.authorization import CashAuthorizationPolicy
from backend.application.cash_register.hardware import CashHardwareGateway
from backend.application.cash_register.permissions import CashPermissions
from backend.domain.cash_register.entities import CashDrawer, CashRegister, PosTerminal
from backend.domain.cash_register.events import CashEvents, cash_event_payload
from backend.shared.ids import new_uuid, validate_uuidv7
from backend.infrastructure.db.repositories.cash_register.unit_of_work import CashRegisterUnitOfWork


def _now() -> str: return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass(frozen=True, slots=True)
class DeviceResult:
    entity_id: str
    message: str
    data: dict | None = None


def _record(uow, event_name: str, *, operation_id: str, entity_id: str,
            branch_id: str, actor_user_id: str, reason: str = "", **extra) -> None:
    event = cash_event_payload(event_name, operation_id=operation_id,
                               entity_id=entity_id, branch_id=branch_id,
                               user_id=actor_user_id, **extra)
    uow.audit.record(audit_id=new_uuid(), action=event_name,
                     actor_user_id=actor_user_id, entity_id=entity_id,
                     branch_id=branch_id, operation_id=operation_id,
                     reason=reason, occurred_at=event["timestamp"])
    uow.events.add(event)
    uow.outbox.enqueue(event)


class CreateCashDeviceUseCase:
    def __init__(self, authorization: CashAuthorizationPolicy) -> None:
        self._auth = authorization

    def execute(self, connection, *, kind: str, branch_id: str, name: str,
                actor_user_id: str, operation_id: str,
                register_id: str | None = None) -> DeviceResult:
        permission = CashPermissions.REGISTER_MANAGE if kind == "register" else (
            CashPermissions.DRAWER_MANAGE if kind == "drawer" else CashPermissions.TERMINAL_MANAGE)
        self._auth.require(user_id=actor_user_id, permission_code=permission, branch_id=branch_id)
        if kind == "register":
            device, event = CashRegister.create(branch_id=branch_id, name=name), CashEvents.REGISTER_CREATED
        elif kind == "drawer":
            device, event = CashDrawer.create(branch_id=branch_id, register_id=register_id, name=name), CashEvents.DRAWER_CREATED
        elif kind == "terminal":
            device, event = PosTerminal.create(branch_id=branch_id, register_id=register_id, name=name), CashEvents.TERMINAL_CREATED
        else: raise ValueError("Unknown cash device kind")
        with CashRegisterUnitOfWork(connection) as uow:
            getattr(uow.devices, f"add_{kind}")(device, now=_now())
            _record(uow, event, operation_id=operation_id, entity_id=device.id,
                    branch_id=branch_id, actor_user_id=actor_user_id)
        return DeviceResult(device.id, "Dispositivo creado")


class SetCashDeviceStatusUseCase:
    def __init__(self, authorization: CashAuthorizationPolicy) -> None: self._auth = authorization

    def execute(self, connection, *, kind: str, device_id: str, branch_id: str,
                activate: bool, actor_user_id: str, operation_id: str,
                reason: str = "") -> DeviceResult:
        permission = CashPermissions.REGISTER_ACTIVATE if activate and kind == "register" else (
            CashPermissions.REGISTER_BLOCK if kind == "register" else
            CashPermissions.DRAWER_MANAGE if kind == "drawer" else CashPermissions.TERMINAL_MANAGE)
        self._auth.require(user_id=actor_user_id, permission_code=permission, branch_id=branch_id)
        events = {
            ("register", True): CashEvents.REGISTER_ACTIVATED, ("register", False): CashEvents.REGISTER_BLOCKED,
            ("drawer", True): CashEvents.DRAWER_ACTIVATED, ("drawer", False): CashEvents.DRAWER_BLOCKED,
            ("terminal", True): CashEvents.TERMINAL_ACTIVATED, ("terminal", False): CashEvents.TERMINAL_BLOCKED,
        }
        with CashRegisterUnitOfWork(connection) as uow:
            if uow.devices.get(kind, device_id) is None: raise LookupError("Dispositivo no encontrado")
            uow.devices.set_status(kind, device_id, "ACTIVE" if activate else "BLOCKED",
                                   reason=reason or None, now=_now())
            _record(uow, events[(kind, activate)], operation_id=operation_id,
                    entity_id=device_id, branch_id=branch_id,
                    actor_user_id=actor_user_id, reason=reason)
        return DeviceResult(device_id, "Estado actualizado")


class AssignCashDeviceUseCase:
    def __init__(self, authorization: CashAuthorizationPolicy) -> None: self._auth = authorization

    def execute(self, connection, *, kind: str, device_id: str, register_id: str,
                branch_id: str, actor_user_id: str, operation_id: str) -> DeviceResult:
        permission = CashPermissions.DRAWER_MANAGE if kind == "drawer" else CashPermissions.TERMINAL_MANAGE
        self._auth.require(user_id=actor_user_id, permission_code=permission, branch_id=branch_id)
        validate_uuidv7(register_id)
        event = CashEvents.DRAWER_ASSIGNED if kind == "drawer" else CashEvents.TERMINAL_ASSIGNED
        with CashRegisterUnitOfWork(connection) as uow:
            register = uow.devices.get("register", register_id)
            device = uow.devices.get(kind, device_id)
            if not register or not device or register["branch_id"] != branch_id or device["branch_id"] != branch_id:
                raise LookupError("Dispositivo o caja fuera de alcance")
            uow.devices.assign(kind, device_id, register_id, now=_now())
            _record(uow, event, operation_id=operation_id, entity_id=device_id,
                    branch_id=branch_id, actor_user_id=actor_user_id,
                    register_id=register_id)
        return DeviceResult(device_id, "Asignación actualizada")


class DiagnoseCashHardwareUseCase:
    def __init__(self, authorization: CashAuthorizationPolicy,
                 gateway: CashHardwareGateway) -> None:
        self._auth, self._gateway = authorization, gateway

    def execute(self, connection, *, device_id: str, branch_id: str,
                actor_user_id: str, operation_id: str):
        self._auth.require(user_id=actor_user_id,
                           permission_code=CashPermissions.HARDWARE_DIAGNOSE,
                           branch_id=branch_id)
        diagnostic = self._gateway.diagnose(device_id)
        with CashRegisterUnitOfWork(connection) as uow:
            _record(uow, CashEvents.HARDWARE_DIAGNOSED,
                    operation_id=operation_id, entity_id=device_id,
                    branch_id=branch_id, actor_user_id=actor_user_id,
                    connected=diagnostic.connected, message=diagnostic.message)
        return diagnostic
