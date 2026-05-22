# core/events/handlers/financial_trace_handler.py — SPJ ERP v13.4
"""
FinancialTraceHandler — trazabilidad financiera end-to-end vía EventBus.

Escucha los eventos canónicos del dominio y delega a FinancialTraceService,
que garantiza que cada operación deje rastro completo:

  evento → documento financiero → tesorería → asiento → bitácora

Prioridad de subscripción: 20 (post-commit, después de handlers críticos).
Todos los handlers de este módulo son async_ (post-commit) para no
interferir con las transacciones de los handlers críticos (p=85-100).

Handlers disponibles:
  SaleTraceHandler          — VENTA_COMPLETADA → trace_sale
  PurchaseTraceHandler      — COMPRA_REGISTRADA → trace_purchase
  PaymentTraceHandler       — payment_confirmed → trace_payment
  PayrollTraceHandler       — NOMINA_PAGADA → trace_payroll
  WasteTraceHandler         — waste_recorded → trace_waste
  LoyaltyTraceHandler       — PUNTOS_ACUMULADOS → trace_loyalty
  DeliveryPaymentHandler    — delivery_payment_confirmed → trace_delivery_payment
  DriverSettlementHandler   — driver_settlement_created → trace_driver_settlement
  MaintenanceTraceHandler   — maintenance_registered → trace_maintenance
  SupplyTraceHandler        — operating_supply_purchased → trace_operating_supply
"""
from __future__ import annotations

import logging
from typing import Any, Dict

logger = logging.getLogger("spj.handlers.financial_trace")


def _build_trace_service(db, finance_services: Dict[str, Any]):
    """Construye FinancialTraceService desde un dict de sub-servicios."""
    from core.services.finance.financial_trace_service import FinancialTraceService
    return FinancialTraceService(
        db=db,
        journal_service=finance_services.get("journal_service"),
        document_service=finance_services.get("document_service"),
        treasury_service=finance_services.get("treasury_movement_service"),
        asset_service=finance_services.get("asset_service"),
        maintenance_service=finance_services.get("maintenance_service"),
        supply_service=finance_services.get("supply_service"),
        idempotency_service=finance_services.get("idempotency_service"),
    )


class SaleTraceHandler:
    """Traza ventas completadas (VENTA_COMPLETADA)."""

    def __init__(self, trace_service):
        self._ts = trace_service

    def handle(self, payload: Dict[str, Any]) -> None:
        try:
            self._ts.trace_sale(payload)
        except Exception as exc:
            logger.error("SaleTraceHandler: %s", exc)


class PurchaseTraceHandler:
    """Traza compras registradas (COMPRA_REGISTRADA)."""

    def __init__(self, trace_service):
        self._ts = trace_service

    def handle(self, payload: Dict[str, Any]) -> None:
        try:
            self._ts.trace_purchase(payload)
        except Exception as exc:
            logger.error("PurchaseTraceHandler: %s", exc)


class PaymentTraceHandler:
    """Traza pagos/cobros confirmados (payment_confirmed)."""

    def __init__(self, trace_service):
        self._ts = trace_service

    def handle(self, payload: Dict[str, Any]) -> None:
        try:
            self._ts.trace_payment(payload)
        except Exception as exc:
            logger.error("PaymentTraceHandler: %s", exc)


class PayrollTraceHandler:
    """Traza nómina pagada (NOMINA_PAGADA)."""

    def __init__(self, trace_service):
        self._ts = trace_service

    def handle(self, payload: Dict[str, Any]) -> None:
        try:
            # Añadir event='paid' si no viene explícito
            p = dict(payload)
            p.setdefault("event", "paid")
            self._ts.trace_payroll(p)
        except Exception as exc:
            logger.error("PayrollTraceHandler: %s", exc)


class WasteTraceHandler:
    """Traza mermas (waste_recorded / MERMA_CREADA)."""

    def __init__(self, trace_service):
        self._ts = trace_service

    def handle(self, payload: Dict[str, Any]) -> None:
        try:
            self._ts.trace_waste(payload)
        except Exception as exc:
            logger.error("WasteTraceHandler: %s", exc)


class LoyaltyTraceHandler:
    """Traza puntos de fidelidad (PUNTOS_ACUMULADOS)."""

    def __init__(self, trace_service):
        self._ts = trace_service

    def handle(self, payload: Dict[str, Any]) -> None:
        try:
            p = dict(payload)
            p.setdefault("event", "earned")
            self._ts.trace_loyalty(p)
        except Exception as exc:
            logger.error("LoyaltyTraceHandler: %s", exc)


class DeliveryPaymentHandler:
    """Traza cobro de delivery confirmado (delivery_payment_confirmed)."""

    def __init__(self, trace_service):
        self._ts = trace_service

    def handle(self, payload: Dict[str, Any]) -> None:
        try:
            self._ts.trace_delivery_payment(payload)
        except Exception as exc:
            logger.error("DeliveryPaymentHandler: %s", exc)


class DriverSettlementHandler:
    """Traza corte de repartidor (driver_settlement_created)."""

    def __init__(self, trace_service):
        self._ts = trace_service

    def handle(self, payload: Dict[str, Any]) -> None:
        try:
            self._ts.trace_driver_settlement(payload)
        except Exception as exc:
            logger.error("DriverSettlementHandler: %s", exc)


class MaintenanceTraceHandler:
    """Traza mantenimientos registrados (maintenance_registered)."""

    def __init__(self, trace_service):
        self._ts = trace_service

    def handle(self, payload: Dict[str, Any]) -> None:
        try:
            self._ts.trace_maintenance(payload)
        except Exception as exc:
            logger.error("MaintenanceTraceHandler: %s", exc)


class SupplyTraceHandler:
    """Traza insumos operativos comprados (operating_supply_purchased)."""

    def __init__(self, trace_service):
        self._ts = trace_service

    def handle(self, payload: Dict[str, Any]) -> None:
        try:
            self._ts.trace_operating_supply(payload)
        except Exception as exc:
            logger.error("SupplyTraceHandler: %s", exc)
