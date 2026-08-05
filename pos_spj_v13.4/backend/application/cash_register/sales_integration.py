"""CASH-9 anti-corruption boundary between Sales events and the cash ledger."""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Mapping

from backend.application.cash_register.ledger_use_cases import LedgerCommandResult
from backend.application.cash_register.shift_use_cases import _record
from backend.domain.cash_register.entities import CashLedgerEntry
from backend.domain.cash_register.enums import CashMovementDirection, CashMovementType
from backend.domain.cash_register.events import CashEvents
from backend.domain.cash_register.exceptions import CashInvalidStateError
from backend.domain.cash_register.settlements import classify_settlement
from backend.infrastructure.db.repositories.cash_register.unit_of_work import CashRegisterUnitOfWork


def _amount(value: object, *, name: str) -> Decimal:
    if isinstance(value, bool):
        raise TypeError(f"{name} must be a monetary value")
    try:
        result = Decimal(str(value or "0"))
    except (InvalidOperation, ValueError) as exc:
        raise ValueError(f"Invalid {name}") from exc
    if not result.is_finite() or result < 0:
        raise ValueError(f"Invalid {name}")
    return result


@dataclass(frozen=True, slots=True)
class SaleCashResult:
    shift_id: str
    ledger_entry_id: str | None
    cash_amount: Decimal
    idempotent: bool = False


class CashSalesIntegrationService:
    """Consumes a completed/cancelled sale without owning Sales business rules."""

    def require_open_shift(self, connection, *, branch_id: str,
                           cashier_user_id: str) -> str:
        shift = CashRegisterUnitOfWork(connection).shifts.find_open_for_cashier(
            branch_id=branch_id, cashier_user_id=cashier_user_id)
        if not shift:
            raise CashInvalidStateError("La venta requiere un turno de caja abierto")
        return shift["id"]

    def record_completed_sale(self, connection, *, sale_id: str, branch_id: str,
                              cashier_user_id: str, operation_id: str,
                              payment_lines: Mapping[str, object],
                              change: object = "0") -> SaleCashResult:
        cash_tendered = Decimal("0")
        for key, value in payment_lines.items():
            definition = classify_settlement(str(key))
            line_amount = _amount(value, name=str(key))
            if definition.affects_drawer:
                cash_tendered += line_amount
        cash_amount = cash_tendered - _amount(change, name="change")
        if cash_amount < 0:
            raise CashInvalidStateError("El cambio no puede exceder el efectivo recibido")
        with CashRegisterUnitOfWork(connection) as uow:
            shift = uow.shifts.find_open_for_cashier(
                branch_id=branch_id, cashier_user_id=cashier_user_id)
            if not shift:
                raise CashInvalidStateError("La venta requiere un turno de caja abierto")
            prior = uow.ledger.find_sale_entry(sale_id)
            if prior:
                return SaleCashResult(shift["id"], prior["id"],
                                      Decimal(prior["amount"]), True)
            if cash_amount == 0:
                return SaleCashResult(shift["id"], None, Decimal("0"))
            entry = CashLedgerEntry.create(
                shift_id=shift["id"], branch_id=branch_id,
                movement_type=CashMovementType.CASH_SALE,
                direction=CashMovementDirection.INFLOW, amount=cash_amount,
                operation_id=operation_id, recorded_by=cashier_user_id,
                concept=f"Venta {sale_id}", reference_id=sale_id)
            uow.ledger.add(entry)
            _record(uow, CashEvents.MOVEMENT_RECORDED, operation_id=operation_id,
                    entity_id=entry.id, branch_id=branch_id,
                    actor_user_id=cashier_user_id, reason=entry.concept,
                    shift_id=shift["id"], movement_type=CashMovementType.CASH_SALE.value,
                    direction=CashMovementDirection.INFLOW.value,
                    amount=str(entry.amount), sale_id=sale_id)
        return SaleCashResult(shift["id"], entry.id, cash_amount)

    def reverse_sale_cash(self, connection, *, sale_id: str, branch_id: str,
                          actor_user_id: str, operation_id: str,
                          reason: str) -> LedgerCommandResult:
        if not reason.strip():
            raise CashInvalidStateError("La cancelación o reverso requiere motivo")
        with CashRegisterUnitOfWork(connection) as uow:
            prior_operation = uow.ledger.get_by_operation(operation_id)
            if prior_operation:
                return LedgerCommandResult(prior_operation["id"], "Compensación ya registrada", True)
            original = uow.ledger.find_sale_entry(sale_id)
            if not original:
                return LedgerCommandResult(sale_id, "Venta sin efectivo; no requiere compensación", True)
            existing = uow.ledger.find_reversal(original["id"])
            if existing:
                return LedgerCommandResult(existing["id"], "Venta ya compensada", True)
            shift = uow.shifts.get(original["shift_id"])
            if not shift or shift["branch_id"] != branch_id:
                raise CashInvalidStateError("El movimiento de venta no pertenece a la sucursal")
            entry = CashLedgerEntry.create(
                shift_id=original["shift_id"], branch_id=branch_id,
                movement_type=CashMovementType.REVERSAL,
                direction=CashMovementDirection.OUTFLOW,
                amount=Decimal(original["amount"]), operation_id=operation_id,
                recorded_by=actor_user_id, concept=reason,
                reference_id=sale_id, reversal_of_id=original["id"])
            uow.ledger.add(entry)
            _record(uow, CashEvents.MOVEMENT_REVERSED, operation_id=operation_id,
                    entity_id=entry.id, branch_id=branch_id,
                    actor_user_id=actor_user_id, reason=reason,
                    shift_id=original["shift_id"], reversal_of_id=original["id"],
                    amount=str(entry.amount), sale_id=sale_id)
        return LedgerCommandResult(entry.id, "Efectivo de venta compensado")

    cancel_sale = reverse_sale_cash
