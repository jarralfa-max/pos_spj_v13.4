"""CASH-12 commands for blind count sessions."""
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal

from backend.application.cash_register.authorization import CashAuthorizationPolicy
from backend.application.cash_register.permissions import CashPermissions
from backend.application.cash_register.shift_use_cases import _record
from backend.domain.cash_register.entities import BlindCashCount
from backend.domain.cash_register.events import CashEvents
from backend.domain.cash_register.exceptions import CashInvalidStateError
from backend.infrastructure.db.repositories.cash_register.unit_of_work import CashRegisterUnitOfWork
from backend.shared.ids import new_uuid


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass(frozen=True, slots=True)
class BlindCountCommandResult:
    entity_id: str
    status: str
    total_counted: Decimal
    idempotent: bool = False


class StartBlindCountUseCase:
    def __init__(self, authorization: CashAuthorizationPolicy) -> None:
        self._auth = authorization

    def execute(self, connection, *, shift_id: str, branch_id: str,
                counter_user_id: str, operation_id: str) -> BlindCountCommandResult:
        self._auth.require(user_id=counter_user_id,
                           permission_code=CashPermissions.BLIND_COUNT_START,
                           branch_id=branch_id)
        with CashRegisterUnitOfWork(connection) as uow:
            prior = uow.counts.get_by_operation(operation_id)
            if prior:
                return BlindCountCommandResult(
                    prior["id"], prior["status"], Decimal(prior["total_counted"]), True)
            shift = uow.shifts.get(shift_id)
            if not shift or shift["branch_id"] != branch_id or shift["status"] not in {
                "OPEN", "CLOSING"
            }:
                raise CashInvalidStateError("El conteo requiere un turno abierto o en cierre preliminar")
            if uow.counts.find_open_for_shift(shift_id):
                raise CashInvalidStateError("El turno ya tiene una sesión de conteo abierta")
            count = BlindCashCount.start(
                shift_id=shift_id, branch_id=branch_id,
                counter_user_id=counter_user_id, operation_id=operation_id)
            uow.counts.add(count)
            _record(uow, CashEvents.BLIND_COUNT_STARTED, operation_id=operation_id,
                    entity_id=count.id, branch_id=branch_id,
                    actor_user_id=counter_user_id, shift_id=shift_id,
                    expected_cash_hidden=True)
        return BlindCountCommandResult(count.id, "OPEN", Decimal("0"))


class CaptureBlindCountDenominationUseCase:
    def __init__(self, authorization: CashAuthorizationPolicy) -> None:
        self._auth = authorization

    def execute(self, connection, *, count_id: str, branch_id: str,
                denomination_id: str, quantity: int, actor_user_id: str,
                operation_id: str) -> BlindCountCommandResult:
        self._auth.require(user_id=actor_user_id,
                           permission_code=CashPermissions.BLIND_COUNT_CAPTURE,
                           branch_id=branch_id)
        if isinstance(quantity, bool) or not isinstance(quantity, int) or quantity < 0:
            raise ValueError("La cantidad debe ser un entero no negativo")
        with CashRegisterUnitOfWork(connection) as uow:
            prior = uow.idempotency.get(operation_id)
            if prior:
                data = json.loads(prior["result_json"])
                return BlindCountCommandResult(
                    count_id, data["status"], Decimal(data["total_counted"]), True)
            count = uow.counts.get(count_id)
            if not count or count["branch_id"] != branch_id or count["status"] != "OPEN":
                raise CashInvalidStateError("La sesión de conteo está bloqueada o no existe")
            denomination = uow.counts.get_active_denomination(
                denomination_id, occurred_at=_now())
            if not denomination:
                raise CashInvalidStateError("Denominación inexistente, inactiva o no vigente")
            uow.counts.capture(
                count_id=count_id, denomination_id=denomination_id,
                denomination=denomination["denomination_value"], quantity=quantity,
                row_id=new_uuid())
            updated = uow.counts.get(count_id)
            result_json = json.dumps({
                "status": updated["status"], "total_counted": updated["total_counted"]})
            uow.idempotency.add(
                operation_id=operation_id, operation_type="BLIND_COUNT_CAPTURE",
                result_entity_id=count_id, result_json=result_json, processed_at=_now())
            _record(uow, CashEvents.BLIND_COUNT_UPDATED, operation_id=operation_id,
                    entity_id=count_id, branch_id=branch_id,
                    actor_user_id=actor_user_id, shift_id=count["shift_id"],
                    denomination_id=denomination_id,
                    denomination=denomination["denomination_value"], quantity=quantity,
                    total_counted=updated["total_counted"], expected_cash_hidden=True)
        return BlindCountCommandResult(
            count_id, updated["status"], Decimal(updated["total_counted"]))


class ConfirmBlindCountUseCase:
    def __init__(self, authorization: CashAuthorizationPolicy) -> None:
        self._auth = authorization

    def execute(self, connection, *, count_id: str, branch_id: str,
                actor_user_id: str, operation_id: str) -> BlindCountCommandResult:
        self._auth.require(user_id=actor_user_id,
                           permission_code=CashPermissions.BLIND_COUNT_CONFIRM,
                           branch_id=branch_id)
        with CashRegisterUnitOfWork(connection) as uow:
            prior = uow.idempotency.get(operation_id)
            if prior:
                data = json.loads(prior["result_json"])
                return BlindCountCommandResult(
                    count_id, "CONFIRMED", Decimal(data["total_counted"]), True)
            count = uow.counts.get(count_id)
            if not count or count["branch_id"] != branch_id or count["status"] != "OPEN":
                raise CashInvalidStateError("La sesión de conteo está bloqueada o no existe")
            if not uow.counts.list_denominations(count_id):
                raise CashInvalidStateError("Capture al menos una denominación antes de confirmar")
            confirmed_at = _now()
            uow.counts.confirm(count_id=count_id, confirmed_at=confirmed_at)
            result_json = json.dumps({"total_counted": count["total_counted"]})
            uow.idempotency.add(
                operation_id=operation_id, operation_type="BLIND_COUNT_CONFIRM",
                result_entity_id=count_id, result_json=result_json, processed_at=confirmed_at)
            _record(uow, CashEvents.BLIND_COUNT_CONFIRMED, operation_id=operation_id,
                    entity_id=count_id, branch_id=branch_id,
                    actor_user_id=actor_user_id, shift_id=count["shift_id"],
                    total_counted=count["total_counted"], expected_cash_hidden=True)
        return BlindCountCommandResult(
            count_id, "CONFIRMED", Decimal(count["total_counted"]))
