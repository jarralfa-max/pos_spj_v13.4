"""CASH-13 generation and printing of non-final X-cut documents."""
from __future__ import annotations

import json
from dataclasses import dataclass
from decimal import Decimal
from typing import Protocol

from backend.application.cash_register.authorization import CashAuthorizationPolicy
from backend.application.cash_register.permissions import CashPermissions
from backend.application.cash_register.shift_use_cases import _record
from backend.domain.cash_register.entities import XCut
from backend.domain.cash_register.events import CashEvents
from backend.domain.cash_register.exceptions import CashInvalidStateError
from backend.infrastructure.db.repositories.cash_register.unit_of_work import CashRegisterUnitOfWork


@dataclass(frozen=True, slots=True)
class XCutCommandResult:
    entity_id: str
    document_number: str
    idempotent: bool = False


def _snapshot(rows: list[dict]) -> tuple[Decimal, dict[str, str]]:
    inflows = outflows = Decimal("0")
    by_type: dict[str, Decimal] = {}
    for row in rows:
        amount = Decimal(row["amount"])
        signed = amount if row["direction"] == "INFLOW" else -amount
        if signed >= 0: inflows += amount
        else: outflows += amount
        by_type[row["movement_type"]] = by_type.get(row["movement_type"], Decimal("0")) + signed
    balance = inflows - outflows
    snapshot = {
        "inflows": str(inflows), "outflows": str(outflows),
        "expected_cash": str(balance), "movement_count": str(len(rows)),
    }
    snapshot.update({f"movement.{key}": str(value) for key, value in sorted(by_type.items())})
    return balance, snapshot


class GenerateXCutUseCase:
    def __init__(self, authorization: CashAuthorizationPolicy) -> None:
        self._auth = authorization

    def execute(self, connection, *, shift_id: str, branch_id: str,
                actor_user_id: str, operation_id: str) -> XCutCommandResult:
        self._auth.require(user_id=actor_user_id,
                           permission_code=CashPermissions.X_CUT_GENERATE,
                           branch_id=branch_id)
        with CashRegisterUnitOfWork(connection) as uow:
            prior = uow.cuts.get_by_operation(operation_id)
            if prior:
                return XCutCommandResult(prior["id"], prior["document_number"], True)
            shift = uow.shifts.get(shift_id)
            if not shift or shift["branch_id"] != branch_id or shift["status"] == "CLOSED":
                raise CashInvalidStateError("El Corte X requiere un turno activo de la sucursal")
            if uow.counts.find_open_for_shift(shift_id):
                raise CashInvalidStateError(
                    "No se puede generar Corte X mientras hay un conteo ciego abierto"
                )
            expected, snapshot = _snapshot(uow.ledger.list_for_shift(shift_id))
            cut = XCut.generate(
                shift_id=shift_id, branch_id=branch_id, generated_by=actor_user_id,
                expected_cash=expected, operation_id=operation_id, snapshot=snapshot)
            uow.cuts.add(cut)
            _record(uow, CashEvents.X_CUT_GENERATED, operation_id=operation_id,
                    entity_id=cut.id, branch_id=branch_id,
                    actor_user_id=actor_user_id, shift_id=shift_id,
                    document_number=cut.document_number,
                    expected_cash=str(cut.expected_cash), final=False,
                    snapshot=cut.snapshot)
        return XCutCommandResult(cut.id, cut.document_number)


class XCutPrintGateway(Protocol):
    def print_document(self, document: dict[str, object]) -> None: ...


class PrintXCutUseCase:
    def __init__(self, authorization: CashAuthorizationPolicy,
                 gateway: XCutPrintGateway) -> None:
        self._auth, self._gateway = authorization, gateway

    def execute(self, connection, *, cut_id: str, branch_id: str,
                actor_user_id: str, operation_id: str,
                reprint: bool = False) -> XCutCommandResult:
        self._auth.require(
            user_id=actor_user_id,
            permission_code=CashPermissions.REPRINT if reprint else CashPermissions.PRINT,
            branch_id=branch_id)
        self._auth.require(user_id=actor_user_id,
                           permission_code=CashPermissions.X_CUT_VIEW,
                           branch_id=branch_id)
        self._auth.require(user_id=actor_user_id,
                           permission_code=CashPermissions.VIEW_SENSITIVE_AMOUNTS,
                           branch_id=branch_id)
        with CashRegisterUnitOfWork(connection) as uow:
            prior = uow.idempotency.get(operation_id)
            if prior:
                data = json.loads(prior["result_json"])
                return XCutCommandResult(cut_id, data["document_number"], True)
            cut = uow.cuts.get(cut_id)
            if not cut or cut["branch_id"] != branch_id or cut["cut_type"] != "X":
                raise CashInvalidStateError("Corte X no encontrado en la sucursal")
            if uow.counts.find_open_for_shift(cut["shift_id"]):
                raise CashInvalidStateError(
                    "No se puede imprimir Corte X mientras hay un conteo ciego abierto"
                )
            document = {
                "cut_id": cut["id"], "document_number": cut["document_number"],
                "shift_id": cut["shift_id"], "branch_id": cut["branch_id"],
                "generated_at": cut["generated_at"], "generated_by": cut["generated_by"],
                "expected_cash": cut["expected_cash"],
                "snapshot": json.loads(cut["snapshot_json"]), "final": False,
            }
            self._gateway.print_document(document)
            uow.idempotency.add(
                operation_id=operation_id,
                operation_type="X_CUT_REPRINT" if reprint else "X_CUT_PRINT",
                result_entity_id=cut_id,
                result_json=json.dumps({"document_number": cut["document_number"]}),
                processed_at=cut["generated_at"])
            _record(uow, CashEvents.X_CUT_PRINTED, operation_id=operation_id,
                    entity_id=cut_id, branch_id=branch_id,
                    actor_user_id=actor_user_id,
                    document_number=cut["document_number"], reprint=reprint)
        return XCutCommandResult(cut_id, cut["document_number"])
