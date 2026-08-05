"""CASH-15 explanation, independent review and resolution workflow."""
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone

from backend.application.cash_register.authorization import CashAuthorizationPolicy
from backend.application.cash_register.permissions import CashPermissions
from backend.application.cash_register.shift_use_cases import _record
from backend.domain.cash_register.events import CashEvents
from backend.domain.cash_register.exceptions import (
    CashInvalidStateError, CashSegregationOfDutiesError,
)
from backend.infrastructure.db.repositories.cash_register.unit_of_work import CashRegisterUnitOfWork


@dataclass(frozen=True, slots=True)
class DifferenceResult:
    entity_id: str
    status: str
    idempotent: bool = False


class _DifferenceTransition:
    permission = ""
    source_status = ""
    target_status = ""
    event_name = ""

    def __init__(self, authorization: CashAuthorizationPolicy) -> None:
        self._auth = authorization

    def _execute(self, connection, *, difference_id: str, branch_id: str,
                 actor_user_id: str, operation_id: str,
                 values: dict[str, object], reason: str) -> DifferenceResult:
        self._auth.require(user_id=actor_user_id, permission_code=self.permission,
                           branch_id=branch_id)
        with CashRegisterUnitOfWork(connection) as uow:
            prior = uow.idempotency.get(operation_id)
            if prior:
                data = json.loads(prior["result_json"])
                return DifferenceResult(difference_id, data["status"], True)
            difference = uow.differences.get(difference_id)
            if not difference or difference["branch_id"] != branch_id:
                raise CashInvalidStateError("Diferencia no encontrada en la sucursal")
            if difference["status"] != self.source_status:
                raise CashInvalidStateError("Estado inválido para la transición de diferencia")
            uow.differences.transition(
                difference_id=difference_id, source_status=self.source_status,
                target_status=self.target_status, values=values)
            uow.idempotency.add(
                operation_id=operation_id, operation_type=self.event_name,
                result_entity_id=difference_id,
                result_json=json.dumps({"status": self.target_status}),
                processed_at=datetime.now(timezone.utc).isoformat(timespec="seconds"))
            _record(uow, self.event_name, operation_id=operation_id,
                    entity_id=difference_id, branch_id=branch_id,
                    actor_user_id=actor_user_id, reason=reason,
                    z_cut_id=difference["z_cut_id"],
                    classification=difference["classification"],
                    severity=difference["severity"],
                    recurrence_count=difference["recurrence_count"])
        return DifferenceResult(difference_id, self.target_status)


class ExplainCashDifferenceUseCase(_DifferenceTransition):
    permission = CashPermissions.DIFFERENCE_EXPLAIN
    source_status, target_status = "DETECTED", "EXPLAINED"
    event_name = CashEvents.DIFFERENCE_EXPLAINED

    def execute(self, connection, *, difference_id: str, branch_id: str,
                actor_user_id: str, operation_id: str,
                explanation: str) -> DifferenceResult:
        if not explanation.strip():
            raise CashInvalidStateError("La explicación es obligatoria")
        return self._execute(
            connection, difference_id=difference_id, branch_id=branch_id,
            actor_user_id=actor_user_id, operation_id=operation_id,
            values={"explanation": explanation.strip(), "explained_by": actor_user_id},
            reason=explanation.strip())


class ReviewCashDifferenceUseCase(_DifferenceTransition):
    permission = CashPermissions.DIFFERENCE_REVIEW
    source_status, target_status = "EXPLAINED", "UNDER_REVIEW"
    event_name = CashEvents.DIFFERENCE_REVIEWED

    def execute(self, connection, *, difference_id: str, branch_id: str,
                actor_user_id: str, operation_id: str) -> DifferenceResult:
        difference = CashRegisterUnitOfWork(connection).differences.get(difference_id)
        if difference and actor_user_id in {difference["detected_by"], difference["explained_by"]}:
            raise CashSegregationOfDutiesError("La revisión requiere un usuario independiente")
        return self._execute(
            connection, difference_id=difference_id, branch_id=branch_id,
            actor_user_id=actor_user_id, operation_id=operation_id,
            values={"reviewed_by": actor_user_id}, reason="Revisión independiente")


class ResolveCashDifferenceUseCase(_DifferenceTransition):
    permission = CashPermissions.DIFFERENCE_RESOLVE
    source_status, target_status = "UNDER_REVIEW", "RESOLVED"
    event_name = CashEvents.DIFFERENCE_RESOLVED

    def execute(self, connection, *, difference_id: str, branch_id: str,
                actor_user_id: str, operation_id: str,
                resolution: str) -> DifferenceResult:
        if not resolution.strip():
            raise CashInvalidStateError("La resolución es obligatoria")
        difference = CashRegisterUnitOfWork(connection).differences.get(difference_id)
        if difference and actor_user_id in {
            difference["detected_by"], difference["explained_by"], difference["reviewed_by"]
        }:
            raise CashSegregationOfDutiesError("La resolución requiere un usuario independiente")
        return self._execute(
            connection, difference_id=difference_id, branch_id=branch_id,
            actor_user_id=actor_user_id, operation_id=operation_id,
            values={"resolution": resolution.strip(), "resolved_by": actor_user_id},
            reason=resolution.strip())
