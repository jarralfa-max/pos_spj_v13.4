"""Canonical Sales event consumers for CASH-9."""
from __future__ import annotations

from decimal import Decimal

from backend.application.cash_register.sales_integration import CashSalesIntegrationService
from backend.application.cash_register.refund_integration import CashRefundIntegrationService
from backend.shared.events.event_contracts import DomainEvent


class SaleCompletedCashHandler:
    def __init__(self, connection, service: CashSalesIntegrationService | None = None) -> None:
        self._connection = connection
        self._service = service or CashSalesIntegrationService()

    def handle(self, event: DomainEvent):
        payload = dict(event.payload)
        settlements = payload.get("settlements")
        if isinstance(settlements, list):
            payment_lines = {}
            for line in settlements:
                key = str(line.get("type") or "")
                payment_lines[key] = Decimal(str(payment_lines.get(key, "0"))) + Decimal(
                    str(line.get("amount", "0")))
        else:
            payment_lines = dict(payload.get("payment_breakdown") or settlements or {})
        if not payment_lines:
            payment_lines = {str(payload.get("payment_method") or ""): payload.get("total", "0")}
        return self._service.record_completed_sale(
            self._connection, sale_id=event.entity_id, branch_id=event.branch_id,
            cashier_user_id=str(event.user_id or ""), operation_id=event.operation_id,
            payment_lines=payment_lines, change=payload.get("change", "0"))


class SaleCancelledCashHandler:
    def __init__(self, connection, service: CashSalesIntegrationService | None = None) -> None:
        self._connection = connection
        self._service = service or CashSalesIntegrationService()

    def handle(self, event: DomainEvent):
        return self._service.reverse_sale_cash(
            self._connection, sale_id=event.entity_id, branch_id=event.branch_id,
            actor_user_id=str(event.user_id or ""), operation_id=event.operation_id,
            reason=str(event.payload.get("reason") or "Venta cancelada/reversada"))


def _settlement_map(value) -> dict[str, object]:
    if isinstance(value, list):
        result: dict[str, Decimal] = {}
        for line in value:
            key = str(line.get("type") or "")
            result[key] = result.get(key, Decimal("0")) + Decimal(str(line.get("amount", "0")))
        return result
    return dict(value or {})


class SaleRefundedCashHandler:
    def __init__(self, connection, service: CashRefundIntegrationService) -> None:
        self._connection, self._service = connection, service

    def handle(self, event: DomainEvent):
        payload = dict(event.payload)
        return self._service.process(
            self._connection,
            refund_id=str(payload.get("refund_id") or ""),
            sale_id=event.entity_id, branch_id=event.branch_id,
            cashier_user_id=str(event.user_id or ""),
            authorized_by=str(payload.get("authorized_by") or ""),
            operation_id=event.operation_id,
            original_payment_lines=_settlement_map(payload.get("original_settlements")),
            refund_lines=_settlement_map(
                payload.get("refund_settlements") or payload.get("settlements")),
            reason=str(payload.get("reason") or "Reembolso de venta"))
