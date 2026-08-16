"""CASH-11 withdrawals, safe drops, custody handovers and alerts."""
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal

from backend.application.cash_register.authorization import CashAuthorizationPolicy
from backend.application.cash_register.ledger_use_cases import LedgerCommandResult
from backend.application.cash_register.permissions import CashPermissions
from backend.application.cash_register.shift_use_cases import _record
from backend.domain.cash_register.entities import CashHandover, CashLedgerEntry
from backend.domain.cash_register.enums import CashMovementDirection, CashMovementType
from backend.domain.cash_register.events import CashEvents
from backend.domain.cash_register.exceptions import (
    CashAuthorizationRequiredError, CashInvalidStateError,
    CashSegregationOfDutiesError,
)
from backend.domain.cash_register.policies.security_policies import (
    CashLimitDecision, CashMonetaryLimitPolicy,
)
from backend.domain.cash_register.policies.workflow_policies import CashShiftLifecyclePolicy
from backend.infrastructure.db.repositories.cash_register.unit_of_work import CashRegisterUnitOfWork
from backend.shared.ids import new_uuid


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _balance(rows: list[dict]) -> Decimal:
    total = Decimal("0")
    for row in rows:
        amount = Decimal(row["amount"])
        total += amount if row["direction"] == "INFLOW" else -amount
    return total


@dataclass(frozen=True, slots=True)
class SafeDropResult:
    entity_id: str
    shift_id: str
    amount: Decimal
    alert_required: bool
    idempotent: bool = False


class RegisterSafeDropUseCase:
    def __init__(self, authorization: CashAuthorizationPolicy,
                 movement_limit: CashMonetaryLimitPolicy,
                 *, alert_threshold: Decimal) -> None:
        if not isinstance(alert_threshold, Decimal) or alert_threshold < 0:
            raise TypeError("alert_threshold must be a non-negative Decimal")
        self._auth, self._limit = authorization, movement_limit
        self._alert_threshold = alert_threshold

    def execute(self, connection, *, shift_id: str, branch_id: str,
                amount: Decimal, reason_code: str, actor_user_id: str,
                operation_id: str, authorized_by: str | None = None) -> SafeDropResult:
        self._auth.require(user_id=actor_user_id,
                           permission_code=CashPermissions.MOVEMENT_SAFE_DROP,
                           branch_id=branch_id)
        decision = self._limit.require_operable(amount)
        with CashRegisterUnitOfWork(connection) as uow:
            prior = uow.ledger.get_by_operation(operation_id)
            if prior:
                return SafeDropResult(prior["id"], prior["shift_id"],
                                      Decimal(prior["amount"]),
                                      Decimal(prior["amount"]) >= self._alert_threshold, True)
            shift = uow.shifts.get(shift_id)
            if not shift or shift["branch_id"] != branch_id:
                raise CashInvalidStateError("El safe drop requiere un turno abierto")
            CashShiftLifecyclePolicy.ensure_operable(shift["status"])
            reason = uow.movement_reasons.get_active(
                code=reason_code, movement_type=CashMovementType.SAFE_DROP.value,
                occurred_at=_now())
            if not reason:
                raise CashInvalidStateError("Motivo de safe drop inexistente, inactivo o no vigente")
            requires_authorization = bool(reason["requires_authorization"]) or (
                decision is CashLimitDecision.REQUIRES_AUTHORIZATION)
            if requires_authorization:
                if not authorized_by:
                    raise CashAuthorizationRequiredError("El safe drop requiere autorización en caliente")
                if authorized_by == actor_user_id:
                    raise CashSegregationOfDutiesError("El autorizador debe ser independiente")
                self._auth.require(
                    user_id=authorized_by,
                    permission_code=CashPermissions.MOVEMENT_AUTHORIZE_OVER_LIMIT,
                    branch_id=branch_id)
            if amount > _balance(uow.ledger.list_for_shift(shift_id)):
                raise CashInvalidStateError("El safe drop excede el efectivo reconstruido del turno")
            entry = CashLedgerEntry.create(
                shift_id=shift_id, branch_id=branch_id,
                movement_type=CashMovementType.SAFE_DROP,
                direction=CashMovementDirection.OUTFLOW, amount=amount,
                operation_id=operation_id, recorded_by=actor_user_id,
                concept=reason["display_name"], reference_id=operation_id)
            uow.ledger.add(entry)
            alert_required = entry.amount >= self._alert_threshold
            _record(uow, CashEvents.SAFE_DROP_RECORDED, operation_id=operation_id,
                    entity_id=entry.id, branch_id=branch_id,
                    actor_user_id=actor_user_id, reason=entry.concept,
                    shift_id=shift_id, amount=str(entry.amount),
                    reason_code=reason["code"], authorized_by=authorized_by,
                    alert_required=alert_required,
                    alert_severity="WARNING" if alert_required else "INFO")
        return SafeDropResult(entry.id, shift_id, entry.amount, alert_required)


@dataclass(frozen=True, slots=True)
class HandoverResult:
    entity_id: str
    status: str
    idempotent: bool = False


def _handover_lines(uow, denominations: dict[str, int]) -> tuple[list[dict], Decimal]:
    if not denominations:
        raise CashInvalidStateError("La entrega requiere desglose por denominaciones")
    lines, total = [], Decimal("0")
    now = _now()
    for denomination_id, quantity in denominations.items():
        if isinstance(quantity, bool) or not isinstance(quantity, int) or quantity < 0:
            raise ValueError("Las cantidades de entrega deben ser enteros no negativos")
        denomination = uow.counts.get_active_denomination(denomination_id, occurred_at=now)
        if not denomination:
            raise CashInvalidStateError("Denominación inexistente, inactiva o no vigente")
        value = Decimal(denomination["denomination_value"])
        subtotal = value * quantity
        total += subtotal
        lines.append({
            "id": new_uuid(), "denomination_id": denomination_id,
            "denomination": str(value), "quantity": quantity,
            "subtotal": str(subtotal),
        })
    return lines, total


def _line_map(lines: list[dict]) -> dict[str, int]:
    return {line["denomination_id"]: int(line["quantity"]) for line in lines}


class PrepareTreasuryHandoverUseCase:
    def __init__(self, authorization: CashAuthorizationPolicy) -> None:
        self._auth = authorization

    def execute(self, connection, *, safe_drop_entry_id: str, branch_id: str,
                actor_user_id: str, operation_id: str,
                denominations: dict[str, int]) -> HandoverResult:
        self._auth.require(user_id=actor_user_id,
                           permission_code=CashPermissions.HANDOVER_PREPARE,
                           branch_id=branch_id)
        with CashRegisterUnitOfWork(connection) as uow:
            prior = uow.handovers.get_by_operation(operation_id)
            if prior:
                return HandoverResult(prior["id"], prior["status"], True)
            source = uow.ledger.get(safe_drop_entry_id)
            if not source or source["branch_id"] != branch_id or source["movement_type"] != "SAFE_DROP":
                raise CashInvalidStateError("La entrega debe originarse en un safe drop de la sucursal")
            lines, total = _handover_lines(uow, denominations)
            if total != Decimal(source["amount"]):
                raise CashInvalidStateError("Las denominaciones no coinciden con el safe drop")
            handover = CashHandover.prepare(
                shift_id=source["shift_id"], branch_id=branch_id,
                amount=Decimal(source["amount"]), prepared_by=actor_user_id,
                operation_id=operation_id, source_entry_id=safe_drop_entry_id)
            uow.handovers.add(handover)
            uow.handovers.add_denominations(handover.id, lines)
            _record(uow, CashEvents.HANDOVER_PREPARED, operation_id=operation_id,
                    entity_id=handover.id, branch_id=branch_id,
                    actor_user_id=actor_user_id, shift_id=handover.shift_id,
                    amount=str(handover.amount), source_entry_id=safe_drop_entry_id,
                    denominations=_line_map(lines))
        return HandoverResult(handover.id, handover.status.value)


class DeliverTreasuryHandoverUseCase:
    def __init__(self, authorization: CashAuthorizationPolicy) -> None:
        self._auth = authorization

    def execute(self, connection, *, handover_id: str, branch_id: str,
                actor_user_id: str, operation_id: str,
                denominations: dict[str, int]) -> HandoverResult:
        self._auth.require(user_id=actor_user_id,
                           permission_code=CashPermissions.HANDOVER_DELIVER,
                           branch_id=branch_id)
        with CashRegisterUnitOfWork(connection) as uow:
            prior = uow.handovers.get_confirmation_by_operation(operation_id)
            if prior: return HandoverResult(handover_id, "DELIVERED", True)
            handover = uow.handovers.get(handover_id)
            if not handover or handover["branch_id"] != branch_id or handover["status"] != "PREPARED":
                raise CashInvalidStateError("La entrega no está preparada")
            lines, total = _handover_lines(uow, denominations)
            prepared = _line_map(uow.handovers.list_denominations(handover_id))
            if _line_map(lines) != prepared or total != Decimal(handover["amount"]):
                raise CashInvalidStateError("La confirmación de entrega no coincide con la preparación")
            now = _now()
            uow.handovers.add_confirmation(
                confirmation_id=new_uuid(), handover_id=handover_id,
                confirmation_type="DELIVERY", confirmed_by=actor_user_id,
                operation_id=operation_id, denominations_json=json.dumps(_line_map(lines), sort_keys=True),
                total_amount=str(total), notes="", confirmed_at=now)
            uow.handovers.transition(
                handover_id=handover_id, source_status="PREPARED", target_status="DELIVERED",
                actor_column="delivered_by", actor_user_id=actor_user_id,
                timestamp_column="delivered_at", timestamp=now)
            _record(uow, CashEvents.HANDOVER_DELIVERED, operation_id=operation_id,
                    entity_id=handover_id, branch_id=branch_id,
                    actor_user_id=actor_user_id, shift_id=handover["shift_id"],
                    amount=handover["amount"], denominations=_line_map(lines),
                    delivery_confirmed=True)
        return HandoverResult(handover_id, "DELIVERED")


class ReceiveTreasuryHandoverUseCase:
    def __init__(self, authorization: CashAuthorizationPolicy) -> None:
        self._auth = authorization

    def execute(self, connection, *, handover_id: str, branch_id: str,
                actor_user_id: str, operation_id: str,
                denominations: dict[str, int]) -> HandoverResult:
        self._auth.require(user_id=actor_user_id,
                           permission_code=CashPermissions.HANDOVER_RECEIVE,
                           branch_id=branch_id)
        with CashRegisterUnitOfWork(connection) as uow:
            prior = uow.handovers.get_confirmation_by_operation(operation_id)
            if prior:
                current = uow.handovers.get(handover_id)
                return HandoverResult(handover_id, current["status"], True)
            handover = uow.handovers.get(handover_id)
            if not handover or handover["branch_id"] != branch_id or handover["status"] != "DELIVERED":
                raise CashInvalidStateError("La entrega no está disponible para recepción")
            if actor_user_id == handover["delivered_by"]:
                raise CashSegregationOfDutiesError("Tesorería debe recibir con un usuario distinto")
            lines, total = _handover_lines(uow, denominations)
            received = _line_map(lines)
            prepared = _line_map(uow.handovers.list_denominations(handover_id))
            matches = received == prepared and total == Decimal(handover["amount"])
            now = _now()
            uow.handovers.add_confirmation(
                confirmation_id=new_uuid(), handover_id=handover_id,
                confirmation_type="RECEPTION", confirmed_by=actor_user_id,
                operation_id=operation_id, denominations_json=json.dumps(received, sort_keys=True),
                total_amount=str(total), notes="" if matches else "Diferencia de recepción",
                confirmed_at=now)
            if matches:
                uow.handovers.transition(
                    handover_id=handover_id, source_status="DELIVERED", target_status="RECEIVED",
                    actor_column="received_by", actor_user_id=actor_user_id,
                    timestamp_column="received_at", timestamp=now)
                event_name, status, reason = CashEvents.HANDOVER_RECEIVED, "RECEIVED", ""
            else:
                reason = "Las denominaciones recibidas no coinciden con la entrega"
                uow.handovers.dispute(
                    handover_id=handover_id, source_status="DELIVERED",
                    disputed_by=actor_user_id, disputed_at=now, reason=reason)
                event_name, status = CashEvents.HANDOVER_DISPUTED, "DISPUTED"
            _record(uow, event_name, operation_id=operation_id,
                    entity_id=handover_id, branch_id=branch_id,
                    actor_user_id=actor_user_id, reason=reason,
                    shift_id=handover["shift_id"], expected_denominations=prepared,
                    received_denominations=received, expected_amount=handover["amount"],
                    received_amount=str(total), treasury_transfer_required=matches)
        return HandoverResult(handover_id, status)


class DisputeTreasuryHandoverUseCase:
    def __init__(self, authorization: CashAuthorizationPolicy) -> None:
        self._auth = authorization

    def execute(self, connection, *, handover_id: str, branch_id: str,
                actor_user_id: str, operation_id: str, reason: str) -> HandoverResult:
        self._auth.require(user_id=actor_user_id,
                           permission_code=CashPermissions.HANDOVER_DISPUTE,
                           branch_id=branch_id)
        if not reason.strip(): raise CashInvalidStateError("La disputa requiere motivo")
        with CashRegisterUnitOfWork(connection) as uow:
            prior = uow.handovers.get_confirmation_by_operation(operation_id)
            if prior: return HandoverResult(handover_id, "DISPUTED", True)
            handover = uow.handovers.get(handover_id)
            if not handover or handover["branch_id"] != branch_id or handover["status"] != "DELIVERED":
                raise CashInvalidStateError("Sólo una entrega confirmada puede disputarse")
            now = _now()
            uow.handovers.add_confirmation(
                confirmation_id=new_uuid(), handover_id=handover_id,
                confirmation_type="DISPUTE", confirmed_by=actor_user_id,
                operation_id=operation_id, denominations_json="{}",
                total_amount="0", notes=reason.strip(), confirmed_at=now)
            uow.handovers.dispute(
                handover_id=handover_id, source_status="DELIVERED",
                disputed_by=actor_user_id, disputed_at=now, reason=reason.strip())
            _record(uow, CashEvents.HANDOVER_DISPUTED, operation_id=operation_id,
                    entity_id=handover_id, branch_id=branch_id,
                    actor_user_id=actor_user_id, reason=reason.strip(),
                    shift_id=handover["shift_id"], treasury_transfer_required=False)
        return HandoverResult(handover_id, "DISPUTED")
