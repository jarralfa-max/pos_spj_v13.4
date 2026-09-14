"""Un pedido con entrega no se confirma sin dirección.

`DeliveryAddressRequiredError` existía y nadie la lanzaba: un pedido a domicilio se
confirmaba sin dirección, y el problema aparecía después, al querer despacharlo sin
saber a dónde ni con qué costo de envío. La regla vive en
`OrderConfirmationPolicy`, y `SetOrderDeliveryAddressUseCase` resuelve la zona para
las MISMAS modalidades (una sola definición).
"""
from __future__ import annotations

import sqlite3
from decimal import Decimal

import pytest

from backend.application.orders_delivery.authorization import OrdersDeliveryAuthorizationPolicy
from backend.application.orders_delivery.permissions import ALL_ORDERS_DELIVERY_PERMISSIONS
from backend.application.orders_delivery.session_authorization import (
    OrdersDeliverySessionPermissionChecker,
)
from backend.application.orders_delivery.use_cases import address_use_cases
from backend.application.orders_delivery.use_cases.order_capture_use_cases import (
    ConfirmCustomerOrderUseCase,
    CreateCustomerOrderUseCase,
)
from backend.domain.orders_delivery.entities import CustomerOrder, CustomerOrderLine
from backend.domain.orders_delivery.enums import (
    FulfillmentType,
    OrderChannel,
    OrderStatus,
    OrderType,
)
from backend.domain.orders_delivery.exceptions import DeliveryAddressRequiredError
from backend.domain.orders_delivery.policies.order_lifecycle_policy import OrderConfirmationPolicy
from backend.domain.orders_delivery.value_objects.order_quantity import OrderQuantity
from backend.infrastructure.db.repositories.orders_delivery.customer_order_repository import (
    CustomerOrderRepository,
)
from backend.infrastructure.db.schema.orders_delivery_schema import (
    create_orders_delivery_schema,
)
from backend.shared.ids import new_uuid
from tests.integration._audit_trail_table import create_audit_logs_table
from tests.integration._delivery_address import give_delivery_address

SUCURSAL = new_uuid()
USUARIO = new_uuid()


class _Sesion:
    is_active = True
    user_id = USUARIO
    active_branch_id = SUCURSAL

    def tiene_permiso(self, code):
        return code in ALL_ORDERS_DELIVERY_PERMISSIONS


POLITICA = OrdersDeliveryAuthorizationPolicy(OrdersDeliverySessionPermissionChecker(_Sesion()))
CON_ENTREGA = sorted(OrderConfirmationPolicy.ADDRESS_REQUIRED_FULFILLMENT_TYPES,
                     key=lambda t: t.value)
SIN_ENTREGA = sorted(set(FulfillmentType) - set(CON_ENTREGA), key=lambda t: t.value)


def _pedido(tipo: FulfillmentType) -> CustomerOrder:
    pedido = CustomerOrder.create(
        branch_id=SUCURSAL, channel=OrderChannel.POS, order_type=OrderType.STANDARD,
        fulfillment_type=tipo, operation_id=new_uuid())
    pedido.add_line(CustomerOrderLine.create(
        order_id=pedido.id, product_id=new_uuid(), unit_price=Decimal("50"),
        requested_quantity=OrderQuantity(Decimal("1"))))
    return pedido


# -- dominio ------------------------------------------------------------------------
def test_the_delivery_modalities_are_the_ones_expected():
    """Fijado a propósito: una modalidad nueva de entrega tiene que decidirse aquí."""
    assert {t.value for t in CON_ENTREGA} == {
        "HOME_DELIVERY", "BRANCH_DELIVERY", "WHOLESALE_DELIVERY", "SCHEDULED_DELIVERY",
        "EXPRESS_DELIVERY", "ROUTE_DELIVERY"}


@pytest.mark.parametrize("tipo", CON_ENTREGA, ids=lambda t: t.value)
def test_a_delivery_order_without_address_is_not_confirmed(tipo):
    pedido = _pedido(tipo)

    with pytest.raises(DeliveryAddressRequiredError):
        pedido.confirm(confirmed_by_user_id=USUARIO)
    assert pedido.status is not OrderStatus.CONFIRMED


@pytest.mark.parametrize("tipo", CON_ENTREGA, ids=lambda t: t.value)
def test_a_delivery_order_with_address_is_confirmed(tipo):
    pedido = _pedido(tipo)
    pedido.set_delivery_address(new_uuid())

    pedido.confirm(confirmed_by_user_id=USUARIO)

    assert pedido.status is OrderStatus.CONFIRMED


@pytest.mark.parametrize("tipo", SIN_ENTREGA, ids=lambda t: t.value)
def test_an_order_without_delivery_needs_no_address(tipo):
    pedido = _pedido(tipo)

    pedido.confirm(confirmed_by_user_id=USUARIO)

    assert pedido.status is OrderStatus.CONFIRMED


def test_the_address_use_case_resolves_zones_for_the_same_modalities():
    assert (address_use_cases._ZONE_REQUIRED_FULFILLMENT_TYPES
            is OrderConfirmationPolicy.ADDRESS_REQUIRED_FULFILLMENT_TYPES)


# -- caso de uso ----------------------------------------------------------------------
@pytest.fixture
def conn():
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    create_orders_delivery_schema(c)
    create_audit_logs_table(c)
    c.commit()
    yield c
    c.close()


def _crear(conn, tipo="HOME_DELIVERY"):
    resultado = CreateCustomerOrderUseCase(POLITICA).execute(
        conn, branch_id=SUCURSAL, channel="POS", order_type="STANDARD", fulfillment_type=tipo,
        lines=[{"product_id": new_uuid(), "unit_price": "80", "requested_quantity": "1"}],
        actor_user_id=USUARIO, operation_id=new_uuid())
    assert resultado.success, resultado.message
    return resultado.entity_id


def _confirmar(conn, pedido):
    return ConfirmCustomerOrderUseCase(POLITICA).execute(
        conn, order_id=pedido, actor_user_id=USUARIO, operation_id=new_uuid())


def test_confirming_without_address_is_refused_and_nothing_changes(conn):
    pedido = _crear(conn)

    resultado = _confirmar(conn, pedido)

    assert resultado.error_code == "DELIVERY_ADDRESS_REQUIRED"
    assert CustomerOrderRepository(conn).get(pedido).status is not OrderStatus.CONFIRMED


def test_confirming_after_the_address_is_set_works(conn):
    pedido = _crear(conn)
    give_delivery_address(conn, pedido, branch_id=SUCURSAL, authorization=POLITICA,
                          actor_user_id=USUARIO)

    resultado = _confirmar(conn, pedido)

    assert resultado.success, resultado.message
    assert CustomerOrderRepository(conn).get(pedido).status is OrderStatus.CONFIRMED
