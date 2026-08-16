"""CASH-9 anti-corruption boundary between Sales events and the cash ledger."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Mapping, Sequence

from backend.application.cash_register.ledger_use_cases import LedgerCommandResult
from backend.application.cash_register.shift_use_cases import _record
from backend.domain.cash_register.entities import CashLedgerEntry, PaymentRecord
from backend.domain.cash_register.enums import (
    CashMovementDirection,
    CashMovementType,
    CashPaymentMethodType,
)
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


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _allocation_type(canonical_type: str) -> CashPaymentMethodType:
    if canonical_type in {"COUPON", "VOUCHER", "PROMOTIONAL_BALANCE"}:
        return CashPaymentMethodType.PROMOTIONAL_VOUCHER
    return CashPaymentMethodType(canonical_type)


def _external_validation_reference(line: Mapping[str, object]) -> str | None:
    reference = (
        line.get("external_reference")
        or line.get("terminal_reference")
        or line.get("instrument_id")
        or line.get("validated_contract_id")
        or line.get("loyalty_contract_id")
        or line.get("coupon_id")
        or line.get("voucher_id")
        or line.get("store_credit_id")
        or line.get("authorization_code")
    )
    return str(reference) if reference else None


def _settlement_lines(payment_lines: object) -> list[dict[str, object]]:
    if isinstance(payment_lines, Mapping):
        rows: list[dict[str, object]] = []
        for key, value in payment_lines.items():
            if isinstance(value, Mapping):
                rows.append({"type": key, **dict(value)})
            else:
                rows.append({"type": key, "amount": value})
        return rows
    if isinstance(payment_lines, Sequence) and not isinstance(payment_lines, (str, bytes, bytearray)):
        rows: list[dict[str, object]] = []
        for index, line in enumerate(payment_lines):
            if not isinstance(line, Mapping):
                raise CashInvalidStateError(f"Línea de pago inválida en posición {index}")
            rows.append(dict(line))
        return rows
    raise CashInvalidStateError("La liquidación de venta requiere líneas de pago")


@dataclass(frozen=True, slots=True)
class SaleCashResult:
    shift_id: str
    ledger_entry_id: str | None
    cash_amount: Decimal
    idempotent: bool = False
    payment_record_id: str | None = None


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
                              payment_lines: object,
                              change: object = "0",
                              amount_to_settle: object | None = None) -> SaleCashResult:
        lines = _settlement_lines(payment_lines)
        if not lines:
            raise CashInvalidStateError("La venta requiere al menos un medio de pago")
        cash_tendered = Decimal("0")
        allocations: list[tuple[CashPaymentMethodType, Decimal, bool, str | None]] = []
        for line in lines:
            raw_type = str(line.get("type") or "")
            definition = classify_settlement(raw_type)
            line_amount = _amount(line.get("amount"), name=raw_type)
            if line_amount == 0:
                continue
            method_type = _allocation_type(definition.canonical_type)
            external_reference = _external_validation_reference(line)
            if definition.requires_external_validation and not external_reference:
                raise CashInvalidStateError(
                    f"{definition.canonical_type} requiere contrato o referencia validada externa"
                )
            if definition.affects_drawer:
                cash_tendered += line_amount
            allocations.append(
                (method_type, line_amount, definition.affects_drawer,
                 str(external_reference) if external_reference else None)
            )
        cash_amount = cash_tendered - _amount(change, name="change")
        if cash_amount < 0:
            raise CashInvalidStateError("El cambio no puede exceder el efectivo recibido")
        if cash_tendered and cash_amount == 0:
            allocations = [
                item for item in allocations
                if not item[2] or item[1] != cash_tendered
            ]
        elif cash_tendered != cash_amount:
            allocations = [
                (method, cash_amount, affects_drawer, reference)
                if affects_drawer else (method, amount, affects_drawer, reference)
                for method, amount, affects_drawer, reference in allocations
            ]
        allocated_total = sum((amount for _, amount, _, _ in allocations), Decimal("0"))
        expected_total = (
            _amount(amount_to_settle, name="amount_to_settle")
            if amount_to_settle is not None else allocated_total
        )
        if expected_total <= 0:
            raise CashInvalidStateError("La liquidación de venta debe ser mayor a cero")
        if allocated_total != expected_total:
            raise CashInvalidStateError(
                "La liquidación de Caja debe coincidir con el total confirmado por Ventas"
            )
        with CashRegisterUnitOfWork(connection) as uow:
            shift = uow.shifts.find_open_for_cashier(
                branch_id=branch_id, cashier_user_id=cashier_user_id)
            if not shift:
                raise CashInvalidStateError("La venta requiere un turno de caja abierto")
            prior_payment = uow.settlements.find_payment_record_for_sale(sale_id)
            prior = uow.ledger.find_sale_entry(sale_id)
            if prior_payment:
                return SaleCashResult(shift["id"], prior["id"] if prior else None,
                                      Decimal(prior["amount"]) if prior else Decimal("0"),
                                      True, prior_payment["id"])
            payment = PaymentRecord.create(
                sale_id=sale_id, shift_id=shift["id"], branch_id=branch_id,
                amount_to_settle=expected_total, operation_id=operation_id,
                recorded_by=cashier_user_id,
            )
            for method_type, amount, affects_drawer, external_reference in allocations:
                payment.add_allocation(
                    method_type=method_type,
                    amount=amount,
                    affects_drawer=affects_drawer,
                    external_reference=external_reference,
                )
            payment.confirm_balanced()
            recorded_at = _now()
            uow.settlements.add_payment_record(
                payment_id=payment.id, sale_id=payment.sale_id,
                shift_id=payment.shift_id, branch_id=payment.branch_id,
                amount_to_settle=str(payment.amount_to_settle),
                operation_id=payment.operation_id,
                recorded_by=payment.recorded_by, recorded_at=recorded_at,
            )
            for allocation in payment.allocations:
                uow.settlements.add_payment_allocation(
                    allocation_id=allocation.id,
                    payment_record_id=payment.id,
                    method_type=allocation.method_type.value,
                    amount=str(allocation.amount),
                    affects_drawer=allocation.affects_drawer,
                    external_reference=allocation.external_reference,
                    created_at=recorded_at,
                )
            entry = None
            if cash_amount > 0:
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
                        amount=str(entry.amount), sale_id=sale_id,
                        payment_record_id=payment.id)
        return SaleCashResult(shift["id"], entry.id if entry else None,
                              cash_amount, payment_record_id=payment.id)

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
