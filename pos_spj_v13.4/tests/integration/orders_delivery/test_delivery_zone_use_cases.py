"""Zonas de entrega (Configuración de Pedidos/Reparto): crear, editar, activar.

LO QUE SE FIJA
--------------
- Una zona creada aquí es la que `SetOrderDeliveryAddressUseCase` resuelve para un
  domicilio: la prueba de extremo a extremo no mira la tabla, mira el costo de
  envío que termina en el pedido.
- Dos zonas ACTIVAS de la sucursal nunca comparten código postal:
  `DeliveryFeePolicy.resolve_zone` toma la primera que encuentra y la consulta no
  ordena, así que el costo dependería del orden de las filas.
- Sin `SETTINGS_MANAGE` no se escribe nada, y una zona de otra sucursal "no existe".

El permiso lo concede una sesión, a través del checker real; ninguna prueba usa
una política permisiva.
"""
from __future__ import annotations

import sqlite3
from decimal import Decimal

import pytest

from backend.application.orders_delivery.authorization import OrdersDeliveryAuthorizationPolicy
from backend.application.orders_delivery.permissions import (
    ALL_ORDERS_DELIVERY_PERMISSIONS,
    OrdersDeliveryPermissions as P,
)
from backend.application.orders_delivery.queries.delivery_zones_query_service import (
    DeliveryZonesQueryService,
)
from backend.application.orders_delivery.session_authorization import (
    OrdersDeliverySessionPermissionChecker,
)
from backend.application.orders_delivery.use_cases.address_use_cases import (
    SetOrderDeliveryAddressUseCase,
)
from backend.application.orders_delivery.use_cases.order_capture_use_cases import (
    CreateCustomerOrderUseCase,
)
from backend.application.orders_delivery.use_cases.zone_use_cases import (
    CreateDeliveryZoneUseCase,
    SetDeliveryZoneActiveUseCase,
    UpdateDeliveryZoneUseCase,
)
from backend.infrastructure.db.schema.orders_delivery_schema import (
    create_orders_delivery_schema,
)
from backend.shared.ids import new_uuid
from tests.integration._audit_trail_table import create_audit_logs_table

SUCURSAL = new_uuid()
OTRA_SUCURSAL = new_uuid()
USUARIO = new_uuid()


class _Sesion:
    is_active = True
    user_id = USUARIO
    active_branch_id = SUCURSAL

    def __init__(self, permisos):
        self.permisos = frozenset(permisos)

    def tiene_permiso(self, code):
        return code in self.permisos


def _politica(permisos):
    return OrdersDeliveryAuthorizationPolicy(
        OrdersDeliverySessionPermissionChecker(_Sesion(permisos)))


GESTOR = _politica(ALL_ORDERS_DELIVERY_PERMISSIONS)
LECTOR = _politica({P.SETTINGS_VIEW})


@pytest.fixture
def conn():
    c = sqlite3.connect(":memory:")
    create_orders_delivery_schema(c)
    create_audit_logs_table(c)
    c.commit()
    yield c
    c.close()


def _crear(conn, politica=GESTOR, **cambios):
    datos = dict(branch_id=SUCURSAL, name="Centro", postal_codes="06000, 06010",
                 minimum_order="100", delivery_fee="35", actor_user_id=USUARIO,
                 operation_id=new_uuid())
    datos.update(cambios)
    return CreateDeliveryZoneUseCase(politica).execute(conn, **datos)


def _editar(conn, zone_id, politica=GESTOR, **cambios):
    datos = dict(zone_id=zone_id, branch_id=SUCURSAL, name="Centro",
                 postal_codes="06000, 06010", minimum_order="100", delivery_fee="35",
                 actor_user_id=USUARIO, operation_id=new_uuid())
    datos.update(cambios)
    return UpdateDeliveryZoneUseCase(politica).execute(conn, **datos)


def _activar(conn, zone_id, active, politica=GESTOR, branch_id=SUCURSAL):
    return SetDeliveryZoneActiveUseCase(politica).execute(
        conn, zone_id=zone_id, branch_id=branch_id, active=active,
        actor_user_id=USUARIO, operation_id=new_uuid())


def _zonas(conn, branch_id=SUCURSAL):
    return DeliveryZonesQueryService(conn).list_for_branch(branch_id)


def _envio_a(conn, postal_code):
    """El flujo real: un pedido a domicilio de $300 y su dirección."""
    pedido = CreateCustomerOrderUseCase(GESTOR).execute(
        conn, branch_id=SUCURSAL, channel="WHATSAPP", order_type="STANDARD",
        fulfillment_type="HOME_DELIVERY",
        lines=[{"product_id": new_uuid(), "unit_price": "300.00", "requested_quantity": "1"}],
        actor_user_id=USUARIO, operation_id=new_uuid())
    assert pedido.success, pedido.message
    return SetOrderDeliveryAddressUseCase(GESTOR).execute(
        conn, order_id=pedido.entity_id, recipient_name="Ana", recipient_phone="5555555555",
        street="Reforma", exterior_number="100", postal_code=postal_code,
        actor_user_id=USUARIO, operation_id=new_uuid())


# -- crear -----------------------------------------------------------------------
def test_a_created_zone_resolves_the_delivery_fee_of_an_address(conn):
    creada = _crear(conn)
    assert creada.success, creada.message

    domicilio = _envio_a(conn, "06010")

    assert domicilio.success, domicilio.message
    assert domicilio.data["order"].grand_total == Decimal("335.00")


def test_creating_a_zone_requires_the_manage_permission(conn):
    resultado = _crear(conn, politica=LECTOR)

    assert not resultado.success
    assert resultado.error_code == "PERMISSION_DENIED"
    assert _zonas(conn) == []


def test_postal_codes_are_trimmed_and_deduplicated(conn):
    _crear(conn, postal_codes=" 06000, 06010 ,06000,, ")

    assert _zonas(conn)[0].postal_codes == ("06000", "06010")


@pytest.mark.parametrize("cambios", [
    {"name": "  "}, {"postal_codes": " , "}, {"delivery_fee": "-1"},
    {"minimum_order": "abc"}, {"estimated_minutes": "12.5"}, {"estimated_minutes": "0"},
    {"maximum_distance_km": "0"},
], ids=["sin_nombre", "sin_codigos", "costo_negativo", "minimo_no_numerico",
        "minutos_fraccion", "minutos_cero", "distancia_cero"])
def test_an_invalid_zone_is_rejected_and_nothing_is_written(conn, cambios):
    resultado = _crear(conn, **cambios)

    assert not resultado.success
    assert resultado.error_code == "INVALID_DELIVERY_ZONE", resultado.message
    assert _zonas(conn) == []


def test_a_new_zone_cannot_take_a_code_of_an_active_zone(conn):
    _crear(conn, name="Centro", postal_codes="06000, 06010")

    resultado = _crear(conn, name="Juárez", postal_codes="06600, 06010")

    assert not resultado.success
    assert resultado.error_code == "DELIVERY_ZONE_OVERLAP"
    assert "06010" in resultado.message and "Centro" in resultado.message
    assert [z.name for z in _zonas(conn)] == ["Centro"]


def test_an_inactive_zone_does_not_block_its_codes(conn):
    vieja = _crear(conn, name="Centro viejo", postal_codes="06000")
    _activar(conn, vieja.entity_id, False)

    assert _crear(conn, name="Centro", postal_codes="06000").success


def test_the_same_codes_in_another_branch_are_not_an_overlap(conn):
    _crear(conn, branch_id=OTRA_SUCURSAL, postal_codes="06000")

    assert _crear(conn, postal_codes="06000").success


# -- editar ----------------------------------------------------------------------
def test_editing_a_zone_changes_the_fee_the_address_gets(conn):
    zona = _crear(conn).entity_id

    editada = _editar(conn, zona, delivery_fee="50", free_delivery_threshold="1000",
                      estimated_minutes="45")

    assert editada.success, editada.message
    [fila] = _zonas(conn)
    assert (Decimal(fila.delivery_fee), fila.estimated_minutes) == (Decimal("50"), 45)
    assert _envio_a(conn, "06000").data["order"].grand_total == Decimal("350.00")


def test_a_zone_does_not_overlap_with_itself(conn):
    zona = _crear(conn, postal_codes="06000, 06010").entity_id

    assert _editar(conn, zona, postal_codes="06010, 06000, 06020").success


def test_editing_cannot_take_a_code_of_another_active_zone(conn):
    _crear(conn, name="Centro", postal_codes="06000")
    juarez = _crear(conn, name="Juárez", postal_codes="06600").entity_id

    resultado = _editar(conn, juarez, name="Juárez", postal_codes="06600, 06000")

    assert resultado.error_code == "DELIVERY_ZONE_OVERLAP"
    assert {z.name: z.postal_codes for z in _zonas(conn)}["Juárez"] == ("06600",)


def test_an_inactive_zone_can_be_edited_onto_taken_codes(conn):
    """Inactiva no resuelve domicilios; el choque se revisa al reactivarla."""
    _crear(conn, name="Centro", postal_codes="06000")
    juarez = _crear(conn, name="Juárez", postal_codes="06600").entity_id
    _activar(conn, juarez, False)

    assert _editar(conn, juarez, name="Juárez", postal_codes="06000").success


# -- activar / desactivar --------------------------------------------------------------
def test_a_deactivated_zone_no_longer_resolves_addresses(conn):
    zona = _crear(conn, postal_codes="06000").entity_id

    assert _activar(conn, zona, False).success

    domicilio = _envio_a(conn, "06000")
    assert domicilio.error_code == "DELIVERY_ZONE_NOT_AVAILABLE"


def test_reactivating_is_refused_when_another_zone_took_its_codes(conn):
    vieja = _crear(conn, name="Centro viejo", postal_codes="06000").entity_id
    _activar(conn, vieja, False)
    _crear(conn, name="Centro", postal_codes="06000")

    resultado = _activar(conn, vieja, True)

    assert resultado.error_code == "DELIVERY_ZONE_OVERLAP"
    assert {z.name: z.active for z in _zonas(conn)} == {"Centro": True, "Centro viejo": False}


def test_reactivating_a_zone_whose_codes_are_free_works(conn):
    zona = _crear(conn, postal_codes="06000").entity_id
    _activar(conn, zona, False)

    assert _activar(conn, zona, True).success
    assert _envio_a(conn, "06000").success


@pytest.mark.parametrize("escribir", [
    lambda conn, zona: _editar(conn, zona, delivery_fee="99"),
    lambda conn, zona: _activar(conn, zona, False),
], ids=["editar", "desactivar"])
def test_a_zone_of_another_branch_is_not_found(conn, escribir):
    ajena = _crear(conn, branch_id=OTRA_SUCURSAL, postal_codes="06000").entity_id

    resultado = escribir(conn, ajena)

    assert resultado.error_code == "DELIVERY_ZONE_NOT_FOUND"
    [fila] = _zonas(conn, OTRA_SUCURSAL)
    assert (Decimal(fila.delivery_fee), fila.active) == (Decimal("35"), True)


@pytest.mark.parametrize("escribir", [
    lambda conn, zona: _editar(conn, zona, politica=LECTOR, delivery_fee="99"),
    lambda conn, zona: _activar(conn, zona, False, politica=LECTOR),
], ids=["editar", "desactivar"])
def test_editing_and_deactivating_require_the_manage_permission(conn, escribir):
    zona = _crear(conn).entity_id

    assert escribir(conn, zona).error_code == "PERMISSION_DENIED"
    [fila] = _zonas(conn)
    assert (Decimal(fila.delivery_fee), fila.active) == (Decimal("35"), True)


def test_the_list_shows_active_zones_first_then_by_name(conn):
    for nombre, codigo in (("Roma", "06700"), ("centro", "06000"), ("Anzures", "11590")):
        _crear(conn, name=nombre, postal_codes=codigo)
    _activar(conn, _zonas(conn)[0].id, False)  # Anzures

    assert [(z.name, z.active) for z in _zonas(conn)] == [
        ("centro", True), ("Roma", True), ("Anzures", False)]
