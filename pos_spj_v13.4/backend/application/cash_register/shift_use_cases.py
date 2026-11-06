"""CASH-7 opening and shift lifecycle on the canonical ledger."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal

from backend.application.cash_register.authorization import CashAuthorizationPolicy
from backend.application.cash_register.permissions import CashPermissions
from backend.domain.cash_register.entities import CashLedgerEntry, CashShift
from backend.domain.cash_register.enums import CashMovementDirection, CashMovementType, CashShiftStatus
from backend.domain.cash_register.events import CashEvents, cash_event_payload
from backend.domain.cash_register.exceptions import (
    CashAuthorizationRequiredError, CashDuplicateOperationError, CashInvalidStateError,
    CashPermissionDeniedError,
)
from backend.domain.cash_register.policies.workflow_policies import CashShiftLifecyclePolicy
from backend.domain.cash_register.policies.security_policies import CashLimitDecision, CashMonetaryLimitPolicy
from backend.infrastructure.db.repositories.cash_register.unit_of_work import CashRegisterUnitOfWork
from backend.shared.ids import new_uuid


@dataclass(frozen=True, slots=True)
class ShiftResult:
    entity_id: str
    message: str
    idempotent: bool = False


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
        # Auditoría CJA-02: cada quien abre SU turno; a nombre de otro, reasignar.
        from backend.application.cash_register.shift_ownership import ensure_can_open_for
        ensure_can_open_for(self._auth, cashier_user_id=cashier_user_id,
                            actor_user_id=actor_user_id, branch_id=branch_id)
        decision = self._limit.require_operable(opening_amount)
        if decision is CashLimitDecision.REQUIRES_AUTHORIZATION:
            raise CashAuthorizationRequiredError(
                "El fondo inicial excede el umbral y requiere autorización independiente")
        with CashRegisterUnitOfWork(connection) as uow:
            # SDLC-ARQ-SHIFT-004: reintentar la misma operación devuelve lo que
            # ya se aplicó, antes de la regla "ya tiene turno".
            prior = uow.shifts.find_by_opening_operation(operation_id)
            if prior:
                if (prior["branch_id"], prior["register_id"], prior["drawer_id"],
                        prior["terminal_id"], prior["cashier_user_id"],
                        Decimal(prior["opening_amount"])) != (
                        branch_id, register_id, drawer_id, terminal_id, cashier_user_id,
                        Decimal(opening_amount)):
                    raise CashDuplicateOperationError(
                        "Esa operación de apertura ya se usó con otros datos.")
                return ShiftResult(prior["id"], "Turno abierto", True)
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
            # SDLC-ARQ-SHIFT-001: la misma fuente que Caja y POS. Por cajero y
            # sin sucursal (decisión SHIFT-004: turnos incompatibles por cajero).
            from backend.application.cash_register.active_shift_resolver import (
                ActiveShiftResolver,
            )
            active = ActiveShiftResolver(uow.connection)
            if active.for_cashier(cashier_user_id=cashier_user_id):
                raise CashInvalidStateError(
                    "El cajero ya tiene un turno activo. Cierra o suspende el turno actual antes de abrir otro.")
            if active.for_resource(column="register_id", value=register_id):
                raise CashInvalidStateError(
                    "La caja seleccionada ya tiene un turno activo. Selecciona otra caja o cierra el turno actual.")
            if active.for_resource(column="drawer_id", value=drawer_id):
                raise CashInvalidStateError(
                    "El cajon seleccionado ya tiene un turno activo. Selecciona otro cajon o cierra el turno actual.")
            if active.for_resource(column="terminal_id", value=terminal_id):
                raise CashInvalidStateError(
                    "La terminal seleccionada ya tiene un turno activo. Selecciona otra terminal o cierra el turno actual.")
            shift = CashShift.open(
                branch_id=branch_id, register_id=register_id, drawer_id=drawer_id,
                terminal_id=terminal_id, cashier_user_id=cashier_user_id,
                opening_amount=opening_amount, operation_id=operation_id)
            uow.shifts.add(shift)
            uow.shifts.add_assignment(
                shift_id=shift.id, branch_id=branch_id, register_id=register_id,
                drawer_id=drawer_id, terminal_id=terminal_id,
                cashier_user_id=cashier_user_id, assigned_by=actor_user_id,
                assigned_at=shift.opened_at)
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
    action_label = "operar"
    target_status: CashShiftStatus
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
            # Auditoría CJA-02: el turno de otro cajero sólo lo interviene un
            # supervisor, con motivo, y queda dicho en el evento.
            from backend.application.cash_register.shift_ownership import (
                ensure_owner_or_intervention,
            )
            intervention = ensure_owner_or_intervention(
                self._auth, shift_cashier_user_id=shift["cashier_user_id"],
                actor_user_id=actor_user_id, branch_id=branch_id,
                intervention_permission=CashPermissions.SHIFT_INTERVENE, reason=reason,
                action=self.action_label)
            CashShiftLifecyclePolicy.ensure_transition(
                current=shift["status"],
                target=self.target_status,
                reason=reason,
            )
            uow.shifts.set_lifecycle(shift_id=shift_id, status=self.target_status.value,
                                     expected_status=shift["status"],
                                     expected_version=shift["version"],
                                     suspended_reason=reason.strip() or None)
            _record(uow, self.event_name, operation_id=operation_id,
                    entity_id=shift_id, branch_id=branch_id,
                    actor_user_id=actor_user_id, reason=reason,
                    intervention=intervention,
                    shift_cashier_user_id=shift["cashier_user_id"])
        return ShiftResult(shift_id, f"Turno {self.target_status.value}")


class ReassignCashShiftUseCase:
    """Entrega de un turno vivo a otro cajero (SDLC-ARQ-SHIFT-003; decisión
    2026-11-02: la entrega existe). El turno, su efectivo y sus movimientos
    siguen siendo los mismos: cambia quién responde de aquí en adelante y cada
    movimiento conserva a quien lo registró. No mueve dinero, así que no hay
    asiento."""

    def __init__(self, authorization: CashAuthorizationPolicy) -> None:
        self._auth = authorization

    def execute(self, connection, *, shift_id: str, branch_id: str,
                new_cashier_user_id: str, actor_user_id: str, operation_id: str,
                reason: str) -> ShiftResult:
        self._auth.require(user_id=actor_user_id,
                           permission_code=CashPermissions.SHIFT_REASSIGN,
                           branch_id=branch_id)
        if not reason.strip():
            raise CashInvalidStateError("Entregar un turno requiere un motivo")
        if not self._auth.has_permission(user_id=new_cashier_user_id,
                                         permission_code=CashPermissions.SHIFT_OPEN,
                                         branch_id=branch_id):
            raise CashPermissionDeniedError(
                "Quien recibe el turno debe poder abrir turnos en esta sucursal.")
        with CashRegisterUnitOfWork(connection) as uow:
            prior = uow.audit.find(action=CashEvents.SHIFT_REASSIGNED,
                                   operation_id=operation_id)
            if prior:
                return ShiftResult(prior["entity_id"], "Turno entregado", True)
            shift = uow.shifts.get(shift_id)
            if not shift or shift["branch_id"] != branch_id:
                raise CashInvalidStateError("Turno no encontrado en la sucursal")
            if shift["cashier_user_id"] == new_cashier_user_id:
                raise CashInvalidStateError("El turno ya es de ese cajero")
            CashShiftLifecyclePolicy.ensure_reassignable(shift["status"])
            from backend.application.cash_register.active_shift_resolver import (
                ActiveShiftResolver,
            )
            if ActiveShiftResolver(uow.connection).for_cashier(
                    cashier_user_id=new_cashier_user_id):
                raise CashInvalidStateError(
                    "Quien recibe ya tiene un turno activo. Debe cerrarlo antes de recibir otro.")
            uow.shifts.reassign(shift_id=shift_id, new_cashier_user_id=new_cashier_user_id,
                                expected_status=shift["status"],
                                expected_version=shift["version"])
            now = datetime.now(timezone.utc).isoformat(timespec="microseconds")
            uow.shifts.end_assignments(shift_id=shift_id, status="REASSIGNED", ended_at=now)
            uow.shifts.add_assignment(
                shift_id=shift_id, branch_id=branch_id, register_id=shift["register_id"],
                drawer_id=shift["drawer_id"], terminal_id=shift["terminal_id"],
                cashier_user_id=new_cashier_user_id, assigned_by=actor_user_id,
                assigned_at=now)
            _record(uow, CashEvents.SHIFT_REASSIGNED, operation_id=operation_id,
                    entity_id=shift_id, branch_id=branch_id,
                    actor_user_id=actor_user_id, reason=reason.strip(),
                    previous_cashier_user_id=shift["cashier_user_id"],
                    cashier_user_id=new_cashier_user_id,
                    register_id=shift["register_id"])
        return ShiftResult(shift_id, "Turno entregado")


class SuspendCashShiftUseCase(_TransitionUseCase):
    permission = CashPermissions.SHIFT_SUSPEND
    action_label = "suspender"
    target_status = CashShiftStatus.SUSPENDED
    event_name = CashEvents.SHIFT_SUSPENDED


class ResumeCashShiftUseCase(_TransitionUseCase):
    permission = CashPermissions.SHIFT_RESUME
    action_label = "reanudar"
    target_status = CashShiftStatus.OPEN
    event_name = CashEvents.SHIFT_RESUMED


class BeginCashShiftClosingUseCase(_TransitionUseCase):
    permission = CashPermissions.SHIFT_PREPARE_CLOSE
    action_label = "pre-cerrar"
    target_status = CashShiftStatus.CLOSING
    event_name = CashEvents.SHIFT_CLOSING_STARTED
