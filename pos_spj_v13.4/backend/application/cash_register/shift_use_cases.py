"""CASH-7 opening and shift lifecycle on the canonical ledger."""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from backend.application.cash_register.authorization import CashAuthorizationPolicy
from backend.application.cash_register.permissions import CashPermissions
from backend.domain.cash_register.entities import CashLedgerEntry, CashShift
from backend.domain.cash_register.enums import CashMovementDirection, CashMovementType
from backend.domain.cash_register.events import CashEvents, cash_event_payload
from backend.domain.cash_register.exceptions import CashAuthorizationRequiredError, CashInvalidStateError
from backend.domain.cash_register.policies.security_policies import CashLimitDecision, CashMonetaryLimitPolicy
from backend.infrastructure.db.repositories.cash_register.unit_of_work import CashRegisterUnitOfWork
from backend.shared.ids import new_uuid


@dataclass(frozen=True, slots=True)
class ShiftResult:
    entity_id: str
    message: str


def _record(uow, event_name, *, operation_id, entity_id, branch_id,
            actor_user_id, reason="", **extra):
    event = cash_event_payload(event_name, operation_id=operation_id,
                               entity_id=entity_id, branch_id=branch_id,
                               user_id=actor_user_id, **extra)
    uow.audit.record(audit_id=new_uuid(), action=event_name,
                     actor_user_id=actor_user_id, entity_id=entity_id,
                     branch_id=branch_id, operation_id=operation_id,
                     reason=reason, occurred_at=event["timestamp"])
    uow.events.add(event)
    uow.outbox.enqueue(event)


class OpenCashShiftUseCase:
    def __init__(self, authorization: CashAuthorizationPolicy,
                 opening_limit: CashMonetaryLimitPolicy) -> None:
        self._auth, self._limit = authorization, opening_limit

    def execute(self, connection, *, branch_id: str, register_id: str,
                drawer_id: str, terminal_id: str, cashier_user_id: str,
                opening_amount: Decimal, actor_user_id: str,
                operation_id: str) -> ShiftResult:
        self._auth.require(user_id=actor_user_id,
                           permission_code=CashPermissions.SHIFT_OPEN,
                           branch_id=branch_id)
        decision = self._limit.require_operable(opening_amount)
        if decision is CashLimitDecision.REQUIRES_AUTHORIZATION:
            raise CashAuthorizationRequiredError(
                "El fondo inicial excede el umbral y requiere autorización independiente")
        with CashRegisterUnitOfWork(connection) as uow:
            register = uow.devices.get("register", register_id)
            drawer = uow.devices.get("drawer", drawer_id)
            terminal = uow.devices.get("terminal", terminal_id)
            if not all((register, drawer, terminal)):
                raise CashInvalidStateError("Caja, cajón y terminal son obligatorios")
            if any(item["branch_id"] != branch_id or item["status"] != "ACTIVE"
                   for item in (register, drawer, terminal)):
                raise CashInvalidStateError("Caja, cajón y terminal deben estar activos en la sucursal")
            if drawer["register_id"] != register_id or terminal["register_id"] != register_id:
                raise CashInvalidStateError("Cajón y terminal deben estar asignados a la caja")
            shift = CashShift.open(
                branch_id=branch_id, register_id=register_id, drawer_id=drawer_id,
                terminal_id=terminal_id, cashier_user_id=cashier_user_id,
                opening_amount=opening_amount, operation_id=operation_id)
            uow.shifts.add(shift)
            if opening_amount > 0:
                uow.ledger.add(CashLedgerEntry.create(
                    shift_id=shift.id, branch_id=branch_id,
                    movement_type=CashMovementType.OPENING_FLOAT,
                    direction=CashMovementDirection.INFLOW, amount=opening_amount,
                    operation_id=operation_id, recorded_by=actor_user_id,
                    reference_id=shift.id))
            _record(uow, CashEvents.SHIFT_OPENED, operation_id=operation_id,
                    entity_id=shift.id, branch_id=branch_id,
                    actor_user_id=actor_user_id, register_id=register_id,
                    drawer_id=drawer_id, terminal_id=terminal_id,
                    cashier_user_id=cashier_user_id,
                    opening_amount=str(opening_amount))
        return ShiftResult(shift.id, "Turno abierto")


class _TransitionUseCase:
    permission = ""
    source_status = ""
    target_status = ""
    event_name = ""

    def __init__(self, authorization: CashAuthorizationPolicy) -> None: self._auth = authorization

    def execute(self, connection, *, shift_id: str, branch_id: str,
                actor_user_id: str, operation_id: str, reason: str = "") -> ShiftResult:
        self._auth.require(user_id=actor_user_id, permission_code=self.permission,
                           branch_id=branch_id)
        with CashRegisterUnitOfWork(connection) as uow:
            shift = uow.shifts.get(shift_id)
            if not shift or shift["branch_id"] != branch_id:
                raise CashInvalidStateError("Turno no encontrado en la sucursal")
            if shift["status"] != self.source_status:
                raise CashInvalidStateError(
                    f"Transición inválida: {shift['status']} → {self.target_status}")
            if self.target_status == "SUSPENDED" and not reason.strip():
                raise CashInvalidStateError("La suspensión requiere motivo")
            uow.shifts.set_lifecycle(shift_id=shift_id, status=self.target_status,
                                     suspended_reason=reason.strip() or None)
            _record(uow, self.event_name, operation_id=operation_id,
                    entity_id=shift_id, branch_id=branch_id,
                    actor_user_id=actor_user_id, reason=reason)
        return ShiftResult(shift_id, f"Turno {self.target_status}")


class SuspendCashShiftUseCase(_TransitionUseCase):
    permission = CashPermissions.SHIFT_SUSPEND
    source_status, target_status = "OPEN", "SUSPENDED"
    event_name = CashEvents.SHIFT_SUSPENDED


class ResumeCashShiftUseCase(_TransitionUseCase):
    permission = CashPermissions.SHIFT_RESUME
    source_status, target_status = "SUSPENDED", "OPEN"
    event_name = CashEvents.SHIFT_RESUMED


class BeginCashShiftClosingUseCase(_TransitionUseCase):
    permission = CashPermissions.SHIFT_PREPARE_CLOSE
    source_status, target_status = "OPEN", "CLOSING"
    event_name = CashEvents.SHIFT_CLOSING_STARTED
