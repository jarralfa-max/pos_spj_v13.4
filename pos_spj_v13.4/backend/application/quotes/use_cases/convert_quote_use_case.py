"""ConvertQuoteToOrderUseCase — la cotización aceptada se vuelve Pedido (CRM-43).

Decisión del usuario (2026-10-09): una cotización aceptada se convierte en un
Pedido tipo ``QUOTE_CONVERTED`` (Pedidos ya lo preveía: tipo y campo
``quote_id`` existían sin productor), canal ``SALES_REP``, a los precios
COTIZADOS. Pedidos lo prepara, lo entrega y lo cobra como venta con su propio
flujo; aquí no se toca ``sales`` ni inventario.

Dos permisos: ``COTIZACIONES.convertir`` y el de Pedidos para crear el pedido
(lo exige el propio caso de uso de Pedidos con su política).

Idempotente: la referencia externa del pedido es el folio de la cotización
(``UNIQUE(channel, external_order_reference)`` en Pedidos), así que un reintento
encuentra el pedido ya creado en vez de duplicarlo.
"""

from __future__ import annotations

from datetime import date

from backend.application.quotes.authorization import QuotesAuthorizationPolicy
from backend.application.quotes.permissions import QuotePermissions
from backend.application.quotes.pricing import QUOTE_CHANNEL
from backend.application.quotes.result import QuoteResult
from backend.domain.quotes.enums import QuoteStatus
from backend.domain.quotes.events import QuoteEvents
from backend.domain.quotes.exceptions import (
    InvalidQuoteStateError,
    QuoteNotFoundError,
    QuotesDomainError,
)
from backend.infrastructure.db.repositories.quotes.unit_of_work import QuotesUnitOfWork
from backend.shared.ids import new_uuid


def order_lines_for(quote) -> list[dict]:
    lines = []
    for line in quote.lines:
        amount = str(line.quantity)
        unit = line.unit_code or "PZA"
        lines.append({
            "product_id": line.product_id,
            "unit_price": str(line.unit_price),
            "requested_quantity": None if line.weighed else amount,
            "requested_quantity_unit": unit,
            "requested_weight": amount if line.weighed else None,
            "requested_weight_unit": unit,
            "catch_weight_enabled": line.weighed,
            "customer_notes": line.notes or None,
            "product_snapshot": {"code": line.product_code, "name": line.description,
                                 "unit": line.unit_code, "quote_line_id": line.id},
        })
    return lines


class ConvertQuoteToOrderUseCase:
    def __init__(self, authorization: QuotesAuthorizationPolicy | None = None,
                 orders_authorization=None) -> None:
        self._auth = authorization or QuotesAuthorizationPolicy()
        self._orders_auth = orders_authorization

    def execute(self, connection, *, actor_user_id: str, quote_id: str, operation_id: str,
                fulfillment_type: str, today: date | None = None) -> QuoteResult:
        from backend.application.orders_delivery.use_cases.order_capture_use_cases import (
            CreateCustomerOrderUseCase,
        )
        from backend.domain.orders_delivery.enums import OrderType
        from backend.infrastructure.db.repositories.customers.unit_of_work import (
            CustomerUnitOfWork,
        )

        try:
            self._auth.require(actor_user_id, QuotePermissions.CONVERT)
            with QuotesUnitOfWork(connection) as uow:
                quote = uow.quotes.get(quote_id)
            if quote is None:
                raise QuoteNotFoundError("La cotización no existe.")
            if quote.status is QuoteStatus.CONVERTED:
                return QuoteResult.ok(
                    f"La cotización ya es el pedido {quote.converted_order_id}.",
                    entity_id=quote.converted_order_id, operation_id=operation_id)
            if quote.status is not QuoteStatus.ACCEPTED:
                raise InvalidQuoteStateError(
                    "Sólo se convierte una cotización aceptada por el cliente.")
            if not fulfillment_type:
                raise InvalidQuoteStateError("Elige cómo se entrega el pedido.")
        except QuotesDomainError as exc:
            return QuoteResult.fail(str(exc), exc.code, operation_id=operation_id)

        customer = CustomerUnitOfWork(connection).customers.get(quote.customer_id)
        order = CreateCustomerOrderUseCase(self._orders_auth).execute(
            connection, branch_id=quote.branch_id, channel=QUOTE_CHANNEL,
            order_type=OrderType.QUOTE_CONVERTED, fulfillment_type=fulfillment_type,
            lines=order_lines_for(quote), actor_user_id=actor_user_id,
            # Pedidos exige un UUIDv7 propio; un reintento lo deduplica la
            # referencia externa (el folio), no este identificador.
            operation_id=new_uuid(), customer_id=quote.customer_id,
            contact_name=getattr(customer, "display_name", None),
            external_order_reference=quote.quote_number, quote_id=quote.id)
        if not order.success:
            return QuoteResult.fail(f"Pedidos no aceptó el pedido: {order.message}",
                                    order.error_code or "ORDER_REJECTED",
                                    operation_id=operation_id)
        try:
            with QuotesUnitOfWork(connection) as uow:
                quote = uow.quotes.get(quote_id)
                quote.convert(order_id=order.entity_id)
                uow.quotes.save(quote)
                uow.audit.record(quote_id=quote.id, action=QuoteEvents.CONVERTED,
                                 actor_user_id=actor_user_id,
                                 detail=f"pedido {order.entity_id}", operation_id=operation_id)
                uow.outbox.enqueue(QuoteEvents.CONVERTED, {
                    "quote_id": quote.id, "quote_number": quote.quote_number,
                    "order_id": order.entity_id, "customer_id": quote.customer_id,
                    "opportunity_id": quote.opportunity_id, "total": str(quote.total),
                    "user_id": actor_user_id}, operation_id)
        except QuotesDomainError as exc:
            return QuoteResult.fail(str(exc), exc.code, operation_id=operation_id)
        return QuoteResult.ok(
            "Pedido creado en borrador en Pedidos: complétalo (entrega, dirección) y "
            "confírmalo ahí.", entity_id=order.entity_id, operation_id=operation_id,
            order_id=order.entity_id)
