"""CaptureOrderUseCase — "Nuevo pedido": el pedido, sus líneas y, si lleva entrega,
su dirección, en UNA transacción.

POR QUÉ NO `CreateCustomerOrderUseCase` + `SetOrderDeliveryAddressUseCase`
-------------------------------------------------------------------------
Cada uno abre y confirma su propia transacción. Encadenados, si la dirección
falla (la zona no cubre el código postal, el pedido no llega al mínimo) el pedido
ya quedó guardado sin dirección, y confirmar un pedido con entrega exige dirección.
Aquí las dos cosas se guardan juntas o no se guarda nada.

EL PRECIO NO LO PONE QUIEN CAPTURA
----------------------------------
`unit_price` sale de Pricing en el servidor (`OrderCaptureCatalogQueryService`);
si la línea trae un precio, se ignora. Un producto sin precio vigente, o no
habilitado para venta en la sucursal, se rechaza.
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Any, Mapping, Sequence

from backend.application.orders_delivery.audit import OrdersDeliveryAuditActions
from backend.application.orders_delivery.dto import CustomerOrderDTO
from backend.application.orders_delivery.permissions import OrdersDeliveryPermissions
from backend.application.orders_delivery.queries.order_capture_catalog_query_service import (
    OrderCaptureCatalogQueryService,
)
from backend.application.orders_delivery.result import OrderResult, fail_from_domain_error
from backend.application.orders_delivery.use_cases._base import _OrdersDeliveryBaseUseCase
from backend.domain.orders_delivery.address import OrderAddress
from backend.domain.orders_delivery.entities import CustomerOrder, CustomerOrderLine
from backend.domain.orders_delivery.enums import FulfillmentType, OrderChannel, OrderType
from backend.domain.orders_delivery.events import OrderEvents
from backend.domain.orders_delivery.exceptions import (
    DeliveryAddressRequiredError,
    InvalidOrderQuantityError,
    InvalidOrderStateError,
    OrderEmptyError,
    OrdersDeliveryDomainError,
    ProductNotAvailableForOrderError,
)
from backend.domain.orders_delivery.policies.delivery_fee_policy import DeliveryFeePolicy
from backend.domain.orders_delivery.policies.order_lifecycle_policy import OrderConfirmationPolicy
from backend.domain.orders_delivery.value_objects.order_quantity import OrderQuantity
from backend.infrastructure.db.repositories.orders_delivery.unit_of_work import (
    OrdersDeliveryUnitOfWork,
)

_ADDRESS_FIELDS = ("recipient_name", "recipient_phone", "street", "exterior_number",
                   "interior_number", "neighborhood", "postal_code", "municipality",
                   "state", "references")


def _enum(tipo, valor, etiqueta):
    try:
        return valor if isinstance(valor, tipo) else tipo(valor)
    except ValueError as exc:
        raise InvalidOrderStateError(f"{etiqueta} desconocido: {valor!r}") from exc


def _cantidad(valor) -> Decimal:
    try:
        return Decimal(str(valor).strip())
    except (InvalidOperation, AttributeError) as exc:
        raise InvalidOrderQuantityError(f"Cantidad inválida: {valor!r}") from exc


class CaptureOrderUseCase(_OrdersDeliveryBaseUseCase):
    def __init__(self, authorization=None, *,
                 catalog_factory=OrderCaptureCatalogQueryService) -> None:
        super().__init__(authorization)
        self._catalog_factory = catalog_factory

    def execute(
        self, connection, *, branch_id: str, channel: OrderChannel | str,
        fulfillment_type: FulfillmentType | str, lines: Sequence[Mapping[str, Any]],
        actor_user_id: str, operation_id: str, contact_name: str | None = None,
        contact_phone: str | None = None, address: Mapping[str, Any] | None = None,
    ) -> OrderResult:
        try:
            self._auth.require(actor_user_id, OrdersDeliveryPermissions.ORDER_CREATE)
            channel = _enum(OrderChannel, channel, "Canal")
            fulfillment_type = _enum(FulfillmentType, fulfillment_type, "Modalidad")
            con_entrega = (fulfillment_type
                           in OrderConfirmationPolicy.ADDRESS_REQUIRED_FULFILLMENT_TYPES)
            if con_entrega:
                self._auth.require(actor_user_id, OrdersDeliveryPermissions.ORDER_EDIT_DRAFT)
                if not address:
                    raise DeliveryAddressRequiredError(
                        "Un pedido con entrega requiere dirección")
            if not lines:
                raise OrderEmptyError("El pedido requiere al menos un producto")
        except OrdersDeliveryDomainError as exc:
            return fail_from_domain_error(exc, operation_id=operation_id)

        catalogo = self._catalog_factory(connection)
        with OrdersDeliveryUnitOfWork(connection) as uow:
            existente = uow.orders.find_by_operation_id(operation_id)
            if existente is not None:
                return OrderResult.ok(
                    "Pedido ya existente (idempotente)", entity_id=existente.id,
                    operation_id=operation_id, order=CustomerOrderDTO.from_entity(existente))
            try:
                pedido = CustomerOrder.create(
                    branch_id=branch_id, channel=channel, order_type=OrderType.STANDARD,
                    fulfillment_type=fulfillment_type, contact_name=contact_name,
                    contact_phone=contact_phone, created_by_user_id=actor_user_id,
                    operation_id=operation_id)
                for linea in lines:
                    pedido.add_line(self._linea(catalogo, pedido, branch_id, linea))
                direccion = None
                if con_entrega:
                    direccion = OrderAddress.create(
                        order_id=pedido.id,
                        **{campo: address.get(campo) for campo in _ADDRESS_FIELDS})
                    zona = DeliveryFeePolicy.resolve_zone(
                        uow.zones.list_active_for_branch(branch_id),
                        postal_code=address.get("postal_code") or "")
                    direccion.assign_zone(zona.id)
                    pedido.set_delivery_fee(DeliveryFeePolicy.calculate_fee(
                        zona, order_subtotal=pedido.totals.subtotal))
                    pedido.set_delivery_address(direccion.id)
            except OrdersDeliveryDomainError as exc:
                return fail_from_domain_error(exc, operation_id=operation_id)

            uow.orders.save(pedido)
            if direccion is not None:
                uow.addresses.save(direccion)
            self._emit(
                uow, OrderEvents.CREATED, aggregate_type="CustomerOrder", entity_id=pedido.id,
                operation_id=operation_id, branch_id=branch_id, actor_user_id=actor_user_id,
                channel=channel.value)
            if direccion is not None:
                self._audit(
                    uow, OrdersDeliveryAuditActions.ORDER_DELIVERY_ADDRESS_SET,
                    entity="CustomerOrder", entity_id=pedido.id, branch_id=branch_id,
                    actor_user_id=actor_user_id, operation_id=operation_id,
                    address_id=direccion.id, delivery_fee=str(pedido.delivery_fee))
        return OrderResult.ok(
            "Pedido creado", entity_id=pedido.id, operation_id=operation_id,
            order=CustomerOrderDTO.from_entity(pedido))

    @staticmethod
    def _linea(catalogo, pedido, branch_id: str, linea: Mapping[str, Any]) -> CustomerOrderLine:
        producto = catalogo.get(branch_id=branch_id, product_id=str(linea.get("product_id") or ""))
        if producto is None:
            raise ProductNotAvailableForOrderError(
                "El producto no está disponible para venta en esta sucursal")
        if producto.price is None:
            raise ProductNotAvailableForOrderError(
                f"«{producto.name}» no tiene precio vigente en esta sucursal")
        cantidad = OrderQuantity(_cantidad(linea.get("quantity")), producto.unit_code or "PZA")
        return CustomerOrderLine.create(
            order_id=pedido.id, product_id=producto.product_id, unit_price=producto.price,
            requested_quantity=None if producto.weighed else cantidad,
            requested_weight=cantidad if producto.weighed else None,
            catch_weight_enabled=producto.catch_weight_enabled or producto.weighed,
            product_snapshot={"code": producto.code, "name": producto.name,
                              "unit": producto.unit_code})
