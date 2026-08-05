"""CASH-14 atomic final Z cut and idempotent post-commit outputs."""
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Protocol

from backend.application.cash_register.authorization import CashAuthorizationPolicy
from backend.application.cash_register.permissions import CashPermissions
from backend.application.cash_register.shift_use_cases import _record
from backend.application.cash_register.x_cut_use_cases import _snapshot
from backend.domain.cash_register.entities import CashDifference, ZCut
from backend.domain.cash_register.difference_policy import CashDifferencePolicy
from backend.domain.cash_register.events import CashEvents
from backend.domain.cash_register.exceptions import CashInvalidStateError
from backend.infrastructure.db.repositories.cash_register.unit_of_work import CashRegisterUnitOfWork
from backend.shared.ids import new_uuid


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass(frozen=True, slots=True)
class ZCutResult:
    entity_id: str
    document_number: str
    difference_id: str | None = None
    idempotent: bool = False


class GenerateZCutUseCase:
    """Consolidates count, difference, shift closure, event and outbox in one UoW."""

    def __init__(self, authorization: CashAuthorizationPolicy) -> None:
        self._auth = authorization

    def execute(self, connection, *, shift_id: str, branch_id: str,
                actor_user_id: str, operation_id: str) -> ZCutResult:
        self._auth.require(user_id=actor_user_id,
                           permission_code=CashPermissions.Z_CUT_GENERATE,
                           branch_id=branch_id)
        with CashRegisterUnitOfWork(connection) as uow:
            prior = uow.cuts.get_by_operation(operation_id)
            if prior:
                difference = uow.differences.find_by_z_cut(prior["id"])
                return ZCutResult(prior["id"], prior["document_number"],
                                  difference["id"] if difference else None, True)
            shift = uow.shifts.get(shift_id)
            if not shift or shift["branch_id"] != branch_id or shift["status"] != "CLOSING":
                raise CashInvalidStateError("El Corte Z requiere cierre preliminar del turno")
            if uow.cuts.find_final_for_shift(shift_id):
                raise CashInvalidStateError("El turno ya tiene un Corte Z final")
            if uow.handovers.unresolved_safe_drop_count(shift_id):
                raise CashInvalidStateError("Existen safe drops pendientes de recepción en Tesorería")
            count = uow.counts.find_confirmed_for_final_cut(shift_id)
            if not count:
                raise CashInvalidStateError("Se requiere un conteo ciego confirmado y no utilizado")
            expected, snapshot = _snapshot(uow.ledger.list_for_shift(shift_id))
            counted = Decimal(count["total_counted"])
            difference_amount = counted - expected
            snapshot.update({
                "counted_cash": str(counted), "difference": str(difference_amount),
                "blind_count_id": count["id"],
                "denominations_json": count["denominations_json"],
            })
            cut = ZCut.generate(
                shift_id=shift_id, branch_id=branch_id, generated_by=actor_user_id,
                expected_cash=expected, counted_cash=counted,
                blind_count_id=count["id"], operation_id=operation_id,
                snapshot=snapshot)
            uow.cuts.add(cut)
            difference = None
            if difference_amount != 0:
                policy_row = uow.difference_policies.resolve(
                    branch_id=branch_id, occurred_at=_now())
                if not policy_row:
                    raise CashInvalidStateError(
                        "No existe una política vigente de tolerancias para diferencias")
                since = (datetime.now(timezone.utc) - timedelta(
                    days=int(policy_row["recurrence_window_days"]))).isoformat(timespec="seconds")
                recurrence = 1 + uow.differences.recurrence_count(
                    branch_id=branch_id,
                    responsible_user_id=shift["cashier_user_id"], since=since)
                policy = CashDifferencePolicy(
                    tolerance=Decimal(policy_row["tolerance_amount"]),
                    critical_threshold=Decimal(policy_row["critical_threshold"]),
                    recurrence_threshold=int(policy_row["recurrence_threshold"]),
                    channels=tuple(json.loads(policy_row["channels_json"])))
                decision = policy.evaluate(difference_amount, recurrence_count=recurrence)
                difference_operation_id = new_uuid()
                difference = CashDifference.detect(
                    shift_id=shift_id, z_cut_id=cut.id, branch_id=branch_id,
                    expected_amount=expected, counted_amount=counted,
                    detected_by=actor_user_id, operation_id=difference_operation_id,
                    responsible_user_id=shift["cashier_user_id"],
                    classification=decision.classification,
                    severity=decision.severity,
                    tolerance_amount=policy.tolerance,
                    recurrence_count=recurrence)
                uow.differences.add(difference)
                _record(uow, CashEvents.DIFFERENCE_DETECTED,
                        operation_id=difference_operation_id,
                        entity_id=difference.id, branch_id=branch_id,
                        actor_user_id=actor_user_id, shift_id=shift_id,
                        z_cut_id=cut.id, responsible_user_id=shift["cashier_user_id"],
                        amount=str(difference_amount),
                        classification=decision.classification.value,
                        severity=decision.severity.value,
                        tolerance_amount=str(policy.tolerance),
                        recurrence_count=recurrence,
                        alert_required=decision.alert_required,
                        channels=decision.channels,
                        whatsapp_required="WHATSAPP" in decision.channels)
            uow.shifts.close(shift_id=shift_id, z_cut_id=cut.id, closed_at=_now())
            _record(uow, CashEvents.Z_CUT_GENERATED, operation_id=operation_id,
                    entity_id=cut.id, branch_id=branch_id,
                    actor_user_id=actor_user_id, shift_id=shift_id,
                    document_number=cut.document_number,
                    expected_cash=str(expected), counted_cash=str(counted),
                    difference=str(difference_amount),
                    difference_id=difference.id if difference else None,
                    blind_count_id=count["id"], final=True,
                    notification_required=True, snapshot=snapshot)
        return ZCutResult(cut.id, cut.document_number,
                          difference.id if difference else None)


class ZCutPrintGateway(Protocol):
    def print_document(self, document: dict[str, object]) -> None: ...


class ZCutNotificationGateway(Protocol):
    def notify(self, document: dict[str, object]) -> None: ...


def _document(cut: dict) -> dict[str, object]:
    return {
        "cut_id": cut["id"], "document_number": cut["document_number"],
        "shift_id": cut["shift_id"], "branch_id": cut["branch_id"],
        "generated_at": cut["generated_at"], "generated_by": cut["generated_by"],
        "expected_cash": cut["expected_cash"], "counted_cash": cut["counted_cash"],
        "difference": cut["difference"], "snapshot": json.loads(cut["snapshot_json"]),
        "final": True,
    }


class PrintZCutUseCase:
    def __init__(self, authorization: CashAuthorizationPolicy,
                 gateway: ZCutPrintGateway) -> None:
        self._auth, self._gateway = authorization, gateway

    def execute(self, connection, *, cut_id: str, branch_id: str,
                actor_user_id: str, operation_id: str,
                reprint: bool = False) -> ZCutResult:
        self._auth.require(
            user_id=actor_user_id,
            permission_code=CashPermissions.Z_CUT_REPRINT if reprint else CashPermissions.PRINT,
            branch_id=branch_id)
        self._auth.require(user_id=actor_user_id,
                           permission_code=CashPermissions.Z_CUT_VIEW,
                           branch_id=branch_id)
        with CashRegisterUnitOfWork(connection) as uow:
            prior = uow.idempotency.get(operation_id)
            if prior:
                data = json.loads(prior["result_json"])
                return ZCutResult(cut_id, data["document_number"], idempotent=True)
            cut = uow.cuts.get(cut_id)
            if not cut or cut["branch_id"] != branch_id or cut["cut_type"] != "Z":
                raise CashInvalidStateError("Corte Z no encontrado en la sucursal")
            self._gateway.print_document(_document(cut))
            uow.idempotency.add(
                operation_id=operation_id,
                operation_type="Z_CUT_REPRINT" if reprint else "Z_CUT_PRINT",
                result_entity_id=cut_id,
                result_json=json.dumps({"document_number": cut["document_number"]}),
                processed_at=_now())
            _record(uow, CashEvents.Z_CUT_PRINTED, operation_id=operation_id,
                    entity_id=cut_id, branch_id=branch_id,
                    actor_user_id=actor_user_id,
                    document_number=cut["document_number"], reprint=reprint)
        return ZCutResult(cut_id, cut["document_number"])


class NotifyZCutUseCase:
    def __init__(self, authorization: CashAuthorizationPolicy,
                 gateway: ZCutNotificationGateway) -> None:
        self._auth, self._gateway = authorization, gateway

    def execute(self, connection, *, cut_id: str, branch_id: str,
                actor_user_id: str, operation_id: str) -> ZCutResult:
        self._auth.require(user_id=actor_user_id,
                           permission_code=CashPermissions.NOTIFICATIONS_MANAGE,
                           branch_id=branch_id)
        with CashRegisterUnitOfWork(connection) as uow:
            prior = uow.idempotency.get(operation_id)
            if prior:
                data = json.loads(prior["result_json"])
                return ZCutResult(cut_id, data["document_number"], idempotent=True)
            cut = uow.cuts.get(cut_id)
            if not cut or cut["branch_id"] != branch_id or cut["cut_type"] != "Z":
                raise CashInvalidStateError("Corte Z no encontrado en la sucursal")
            self._gateway.notify(_document(cut))
            uow.idempotency.add(
                operation_id=operation_id, operation_type="Z_CUT_NOTIFY",
                result_entity_id=cut_id,
                result_json=json.dumps({"document_number": cut["document_number"]}),
                processed_at=_now())
            _record(uow, CashEvents.Z_CUT_NOTIFICATION_SENT,
                    operation_id=operation_id, entity_id=cut_id,
                    branch_id=branch_id, actor_user_id=actor_user_id,
                    document_number=cut["document_number"])
        return ZCutResult(cut_id, cut["document_number"])
