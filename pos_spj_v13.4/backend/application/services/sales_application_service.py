"""Canonical application service for sales creation."""

from __future__ import annotations

import logging
from typing import Any, Mapping, Protocol

from backend.application.commands.sales_commands import CreateSaleCommand
from backend.application.dto.use_case_result import UseCaseResult
from backend.shared.events.event_bus import EventBus, InMemoryEventBus
from backend.shared.events.event_contracts import create_domain_event
from backend.shared.events.event_names import EventName
from core.use_cases.venta import DatosPago, ItemCarrito, ResultadoVenta

logger = logging.getLogger(__name__)


class SaleProcessorProtocol(Protocol):
    def ejecutar(self, items: list[ItemCarrito], datos_pago: DatosPago, sucursal_id: str, usuario: str) -> ResultadoVenta: ...


class SalesApplicationService:
    """Coordinates the canonical sale use case without duplicating business rules.

    The existing and protected sales business flow remains in
    ``core.use_cases.venta.ProcesarVentaUC`` and ``core.services.sales_service``.
    This service is an application-layer adapter so desktop and future API
    callers can use the same English command contract.
    """

    def __init__(self, *, sale_processor: SaleProcessorProtocol, event_bus: EventBus | None = None) -> None:
        self._sale_processor = sale_processor
        self._event_bus = event_bus or InMemoryEventBus()

    def create(self, command: CreateSaleCommand) -> UseCaseResult:
        command.validate_context()
        if not command.items:
            return UseCaseResult(False, command.operation_id, message="SALE_ITEMS_REQUIRED")

        try:
            items = [self._to_item(item) for item in command.items]
            payment = dict(command.payment or {})
            datos_pago = DatosPago(
                forma_pago=str(payment.get("payment_method") or payment.get("forma_pago") or "Efectivo"),
                monto_pagado=float(payment.get("amount_paid") or payment.get("monto_pagado") or 0.0),
                total_pagado=float(payment.get("total_paid") or payment.get("total_pagado") or payment.get("amount_paid") or 0.0),
                pago_mixto=dict(payment.get("payment_lines") or payment.get("pago_mixto") or {}),
                payment_breakdown=dict(payment.get("payment_breakdown") or payment.get("breakdown") or payment.get("payment_lines") or {}),
                cliente_id=command.customer_id or None,
                descuento_global=float(payment.get("discount") or payment.get("descuento") or 0.0),
                puntos_canjeados=int(payment.get("loyalty_points_redeemed") or payment.get("puntos_canjeados") or 0),
                descuento_puntos=float(payment.get("loyalty_discount") or payment.get("descuento_puntos") or 0.0),
                notas=command.notes,
                sucursal_id=command.branch_id,
                usuario=command.user_name or command.user_id or "",
                operation_id=command.operation_id,
                reserva_id=command.reservation_id or None,
            )
            result = self._sale_processor.ejecutar(
                items,
                datos_pago,
                str(command.branch_id),
                command.user_name or command.user_id or "",
            )
        except Exception:
            logger.exception("[SALES] canonical sale execution failed operation_id=%s", command.operation_id)
            return UseCaseResult(False, command.operation_id, message="SALE_CREATE_FAILED")

        if not getattr(result, "ok", False):
            return UseCaseResult(False, command.operation_id, message=str(getattr(result, "error", "SALE_CREATE_FAILED") or "SALE_CREATE_FAILED"))

        operation_id = str(getattr(result, "operation_id", "") or command.operation_id)
        event = create_domain_event(
            event_name=EventName.SALE_COMPLETED,
            operation_id=operation_id,
            entity_id=str(getattr(result, "venta_id", "") or ""),
            branch_id=str(command.branch_id),
            user_id=command.user_id,
            user_name=command.user_name,
            source_module="sales",
            payload={
                "sale_id": getattr(result, "venta_id", "") or "",
                "folio": getattr(result, "folio", ""),
                "total": getattr(result, "total", 0.0),
                "change": getattr(result, "cambio", 0.0),
                "payment_breakdown": dict(getattr(result, "payment_breakdown", {}) or {}),
            },
        )
        events = ()
        try:
            self._event_bus.publish(event)
            events = (event,)
        except Exception:
            logger.exception("[SALES] event publish failed operation_id=%s sale_id=%s", operation_id, getattr(result, "venta_id", ""))

        return UseCaseResult(
            True,
            operation_id,
            entity_id=str(getattr(result, "venta_id", "") or ""),
            message="SALE_COMPLETED",
            data={
                "sale_id": getattr(result, "venta_id", "") or "",
                "folio": getattr(result, "folio", ""),
                "total": getattr(result, "total", 0.0),
                "change": getattr(result, "cambio", 0.0),
                "ticket_payload": dict(getattr(result, "ticket_payload", {}) or {}),
            },
            events=events,
        )

    @staticmethod
    def _to_item(item: Mapping[str, Any]) -> ItemCarrito:
        return ItemCarrito(
            producto_id=str(item.get("product_id") or item.get("id") or ""),
            cantidad=float(item.get("quantity") or item.get("qty") or item.get("cantidad") or 0.0),
            precio_unit=float(item.get("unit_price") or item.get("precio_unitario") or item.get("precio_unit") or 0.0),
            nombre=str(item.get("name") or item.get("nombre") or ""),
            es_compuesto=int(item.get("is_composite") or item.get("es_compuesto") or 0),
            descuento=float(item.get("discount") or item.get("descuento") or 0.0),
        )
