"""CASH-17 refund boundary: original settlement validation and physical cash outflow."""
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from typing import Mapping

from backend.application.cash_register.authorization import CashAuthorizationPolicy
from backend.application.cash_register.permissions import CashPermissions
from backend.application.cash_register.sales_integration import _amount
from backend.application.cash_register.shift_use_cases import _record
from backend.domain.cash_register.entities import CashLedgerEntry
from backend.domain.cash_register.enums import CashMovementDirection, CashMovementType
from backend.domain.cash_register.events import CashEvents
from backend.domain.cash_register.exceptions import CashInvalidStateError
from backend.domain.cash_register.policies.security_policies import (
    CashMonetaryLimitPolicy, CashSegregationOfDutiesPolicy,
)
from backend.domain.cash_register.settlements import classify_settlement
from backend.infrastructure.db.repositories.cash_register.unit_of_work import CashRegisterUnitOfWork


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _classified(lines: Mapping[str, object]) -> dict[str, Decimal]:
    result: dict[str, Decimal] = {}
    for raw_type, raw_amount in lines.items():
        definition = classify_settlement(str(raw_type))
        amount = _amount(raw_amount, name=str(raw_type))
        result[definition.canonical_type] = result.get(
            definition.canonical_type, Decimal("0")) + amount
    return result


def _drawer_balance(rows: list[dict]) -> Decimal:
    return sum((
        Decimal(row["amount"]) if row["direction"] == "INFLOW"
        else -Decimal(row["amount"]) for row in rows), Decimal("0"))


@dataclass(frozen=True, slots=True)
class CashRefundResult:
    refund_id: str
    ledger_entry_id: str | None
    cash_amount: Decimal
    idempotent: bool = False


class CashRefundIntegrationService:
    def __init__(self, authorization: CashAuthorizationPolicy,
                 refund_limit: CashMonetaryLimitPolicy) -> None:
        self._auth, self._limit = authorization, refund_limit
        self._segregation = CashSegregationOfDutiesPolicy()

    def process(self, connection, *, refund_id: str, sale_id: str,
                branch_id: str, cashier_user_id: str, authorized_by: str,
                operation_id: str, original_payment_lines: Mapping[str, object],
                refund_lines: Mapping[str, object], reason: str) -> CashRefundResult:
        self._auth.require(user_id=cashier_user_id,
                           permission_code=CashPermissions.REFUND_REQUEST,
                           branch_id=branch_id)
        self._segregation.refund_requester_requires_independent_authorizer(
            cashier_user_id, authorized_by)
        self._auth.require(user_id=authorized_by,
                           permission_code=CashPermissions.REFUND_AUTHORIZE,
                           branch_id=branch_id)
        if not reason.strip():
            raise CashInvalidStateError("El reembolso requiere motivo")
        original, requested = _classified(original_payment_lines), _classified(refund_lines)
        for settlement_type, amount in requested.items():
            if amount > original.get(settlement_type, Decimal("0")):
                raise CashInvalidStateError(
                    f"El reembolso excede el pago original para {settlement_type}")
        cash_amount = requested.get("CASH", Decimal("0"))
        self._limit.require_operable(cash_amount)
        with CashRegisterUnitOfWork(connection) as uow:
            prior = uow.idempotency.get(operation_id)
            if prior:
                data = json.loads(prior["result_json"])
                return CashRefundResult(
                    refund_id, data.get("ledger_entry_id"),
                    Decimal(data["cash_amount"]), True)
            if uow.ledger.find_refund_entry(refund_id):
                raise CashInvalidStateError("El reembolso ya fue registrado con otra operación")
            shift = uow.shifts.find_open_for_cashier(
                branch_id=branch_id, cashier_user_id=cashier_user_id)
            if not shift:
                raise CashInvalidStateError("El reembolso requiere un turno abierto")
            entry = None
            if cash_amount > 0:
                original_cash = uow.ledger.find_sale_entry(sale_id)
                if not original_cash:
                    raise CashInvalidStateError("La venta original no recibió efectivo en Caja")
                refunded = uow.ledger.refunded_cash_for_sale(sale_id)
                if refunded + cash_amount > Decimal(original_cash["amount"]):
                    raise CashInvalidStateError("El efectivo acumulado reembolsado excede la venta original")
                if cash_amount > _drawer_balance(uow.ledger.list_for_shift(shift["id"])):
                    raise CashInvalidStateError("No hay efectivo suficiente en el cajón para el reembolso")
                entry = CashLedgerEntry.create(
                    shift_id=shift["id"], branch_id=branch_id,
                    movement_type=CashMovementType.CASH_REFUND,
                    direction=CashMovementDirection.OUTFLOW, amount=cash_amount,
                    operation_id=operation_id, recorded_by=cashier_user_id,
                    concept=reason, reference_id=refund_id,
                    related_sale_id=sale_id)
                uow.ledger.add(entry)
            result_entity_id = entry.id if entry else refund_id
            result_data = {
                "ledger_entry_id": entry.id if entry else None,
                "cash_amount": str(cash_amount),
            }
            uow.idempotency.add(
                operation_id=operation_id, operation_type="SALE_REFUND_CASH",
                result_entity_id=result_entity_id,
                result_json=json.dumps(result_data), processed_at=_now())
            _record(uow, CashEvents.REFUND_PROCESSED, operation_id=operation_id,
                    entity_id=refund_id, branch_id=branch_id,
                    actor_user_id=cashier_user_id, reason=reason.strip(),
                    sale_id=sale_id, shift_id=shift["id"],
                    ledger_entry_id=entry.id if entry else None,
                    cash_amount=str(cash_amount),
                    original_settlements={key: str(value) for key, value in original.items()},
                    refund_settlements={key: str(value) for key, value in requested.items()},
                    authorized_by=authorized_by,
                    finance_event="SALE_REFUNDED",
                    loyalty_reversal_required="LOYALTY_POINTS" in requested)
        return CashRefundResult(refund_id, entry.id if entry else None, cash_amount)
