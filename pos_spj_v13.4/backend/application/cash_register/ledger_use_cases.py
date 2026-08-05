"""CASH-8 commands for the immutable, reconstructible cash ledger."""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from backend.application.cash_register.authorization import CashAuthorizationPolicy
from backend.application.cash_register.permissions import CashPermissions
from backend.application.cash_register.shift_use_cases import _record
from backend.domain.cash_register.entities import CashLedgerEntry
from backend.domain.cash_register.enums import CashMovementDirection, CashMovementType
from backend.domain.cash_register.events import CashEvents
from backend.domain.cash_register.exceptions import (
    CashAuthorizationRequiredError, CashDuplicateOperationError, CashInvalidStateError,
)
from backend.domain.cash_register.policies.security_policies import (
    CashLimitDecision, CashMonetaryLimitPolicy, CashSegregationOfDutiesPolicy,
)
from backend.infrastructure.db.repositories.cash_register.unit_of_work import CashRegisterUnitOfWork


@dataclass(frozen=True, slots=True)
class LedgerCommandResult:
    entity_id: str
    message: str
    idempotent: bool = False


_MANUAL_MOVEMENTS = {
    CashMovementType.MANUAL_INCOME: (CashMovementDirection.INFLOW, CashPermissions.MOVEMENT_INCOME),
    CashMovementType.MANUAL_WITHDRAWAL: (CashMovementDirection.OUTFLOW, CashPermissions.MOVEMENT_WITHDRAWAL),
    CashMovementType.SAFE_DROP: (CashMovementDirection.OUTFLOW, CashPermissions.MOVEMENT_SAFE_DROP),
}


class RegisterCashMovementUseCase:
    def __init__(self, authorization: CashAuthorizationPolicy,
                 movement_limit: CashMonetaryLimitPolicy) -> None:
        self._auth, self._limit = authorization, movement_limit

    def execute(self, connection, *, shift_id: str, branch_id: str,
                movement_type: CashMovementType, amount: Decimal, concept: str,
                actor_user_id: str, operation_id: str,
                authorized_by: str | None = None) -> LedgerCommandResult:
        try:
            direction, permission = _MANUAL_MOVEMENTS[movement_type]
        except (KeyError, TypeError) as exc:
            raise CashInvalidStateError("Tipo de movimiento manual no permitido") from exc
        self._auth.require(user_id=actor_user_id, permission_code=permission,
                           branch_id=branch_id)
        if not concept.strip():
            raise CashInvalidStateError("El concepto del movimiento es obligatorio")
        decision = self._limit.require_operable(amount)
        if decision is CashLimitDecision.REQUIRES_AUTHORIZATION:
            if not authorized_by:
                raise CashAuthorizationRequiredError("El movimiento requiere autorización en caliente")
            CashSegregationOfDutiesPolicy().reversal_requires_independent_authorizer(
                actor_user_id, authorized_by)
            self._auth.require(user_id=authorized_by,
                               permission_code=CashPermissions.MOVEMENT_AUTHORIZE_OVER_LIMIT,
                               branch_id=branch_id)
        with CashRegisterUnitOfWork(connection) as uow:
            prior = uow.ledger.get_by_operation(operation_id)
            if prior:
                return LedgerCommandResult(prior["id"], "Movimiento ya registrado", True)
            shift = uow.shifts.get(shift_id)
            if not shift or shift["branch_id"] != branch_id or shift["status"] != "OPEN":
                raise CashInvalidStateError("El turno debe estar abierto en la sucursal")
            entry = CashLedgerEntry.create(
                shift_id=shift_id, branch_id=branch_id, movement_type=movement_type,
                direction=direction, amount=amount, operation_id=operation_id,
                recorded_by=actor_user_id, concept=concept)
            uow.ledger.add(entry)
            _record(uow, CashEvents.MOVEMENT_RECORDED, operation_id=operation_id,
                    entity_id=entry.id, branch_id=branch_id,
                    actor_user_id=actor_user_id, reason=concept,
                    shift_id=shift_id, movement_type=movement_type.value,
                    direction=direction.value, amount=str(entry.amount),
                    authorized_by=authorized_by)
        return LedgerCommandResult(entry.id, "Movimiento registrado")


class ReverseCashMovementUseCase:
    def __init__(self, authorization: CashAuthorizationPolicy,
                 segregation: CashSegregationOfDutiesPolicy | None = None) -> None:
        self._auth = authorization
        self._segregation = segregation or CashSegregationOfDutiesPolicy()

    def execute(self, connection, *, entry_id: str, branch_id: str,
                actor_user_id: str, authorized_by: str, operation_id: str,
                reason: str) -> LedgerCommandResult:
        self._auth.require(user_id=actor_user_id,
                           permission_code=CashPermissions.MOVEMENT_REVERSE,
                           branch_id=branch_id)
        self._segregation.reversal_requires_independent_authorizer(actor_user_id, authorized_by)
        self._auth.require(user_id=authorized_by,
                           permission_code=CashPermissions.MOVEMENT_AUTHORIZE_OVER_LIMIT,
                           branch_id=branch_id)
        if not reason.strip():
            raise CashInvalidStateError("El reverso requiere un motivo")
        with CashRegisterUnitOfWork(connection) as uow:
            prior_operation = uow.ledger.get_by_operation(operation_id)
            if prior_operation:
                return LedgerCommandResult(prior_operation["id"], "Reverso ya registrado", True)
            original = uow.ledger.get(entry_id)
            if not original or original["branch_id"] != branch_id:
                raise CashInvalidStateError("Movimiento no encontrado en la sucursal")
            if original["movement_type"] == CashMovementType.REVERSAL.value:
                raise CashInvalidStateError("Un reverso no puede reversarse")
            if uow.ledger.find_reversal(entry_id):
                raise CashDuplicateOperationError("El movimiento ya fue reversado")
            shift = uow.shifts.get(original["shift_id"])
            if not shift or shift["status"] != "OPEN":
                raise CashInvalidStateError("Sólo se reversan movimientos de un turno abierto")
            opposite = (CashMovementDirection.OUTFLOW
                        if original["direction"] == CashMovementDirection.INFLOW.value
                        else CashMovementDirection.INFLOW)
            entry = CashLedgerEntry.create(
                shift_id=original["shift_id"], branch_id=branch_id,
                movement_type=CashMovementType.REVERSAL, direction=opposite,
                amount=Decimal(original["amount"]), operation_id=operation_id,
                recorded_by=actor_user_id, concept=reason,
                reference_id=original["reference_id"], reversal_of_id=entry_id)
            uow.ledger.add(entry)
            _record(uow, CashEvents.MOVEMENT_REVERSED, operation_id=operation_id,
                    entity_id=entry.id, branch_id=branch_id,
                    actor_user_id=actor_user_id, reason=reason,
                    shift_id=original["shift_id"], reversal_of_id=entry_id,
                    amount=str(entry.amount), authorized_by=authorized_by)
        return LedgerCommandResult(entry.id, "Movimiento reversado")
