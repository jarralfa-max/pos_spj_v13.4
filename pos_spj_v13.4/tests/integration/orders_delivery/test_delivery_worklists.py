"""Bandejas de reparto (PASS 6): la fuente es el trabajo, no el pedido.

LOS DOS BADGES QUE SE CORRIGEN
------------------------------
"Entregas activas" y "Entregas fallidas" contaban sobre `customer_orders`:

- `fulfillment_status='FAILED'` sólo lo escribe la reserva de INVENTARIO fallida.
- Un intento de entrega fallido no toca el pedido, que queda `DISPATCHED`.

Así que la siembra incluye justo lo que distingue la versión vieja de la nueva:
DOS pedidos con la reserva fallida y sin trabajo (el badge viejo contaba 2
entregas fallidas; hay 1) y un trabajo fallido cuyo pedido está `DISPATCHED` (el
badge viejo lo contaba como entrega activa).

Como en las bandejas de pedidos, todo se siembra CONDUCIENDO el dominio
—`assign_driver`, `dispatch`, `record_attempt`…— y guardando con el repositorio.
"""
from __future__ import annotations

import sqlite3
from decimal import Decimal
from itertools import combinations

import pytest

from backend.application.orders_delivery.queries.delivery_jobs_worklist_query_service import (
    DeliveryJobsWorklistQueryService,
)
from backend.application.orders_delivery.queries.delivery_worklists import DeliveryWorklist
from backend.application.orders_delivery.queries.order_badge_query_service import (
    OrdersDeliveryBadgeQueryService,
)
from backend.domain.orders_delivery.delivery_job import DeliveryAttempt, DeliveryJob
from backend.domain.orders_delivery.entities import CustomerOrder, CustomerOrderLine
from backend.domain.orders_delivery.enums import FulfillmentType, OrderChannel, OrderType
from backend.domain.orders_delivery.value_objects.delivery_evidence import DeliveryEvidence
from backend.domain.orders_delivery.value_objects.order_quantity import OrderQuantity
from backend.infrastructure.db.repositories.orders_delivery.customer_order_repository import (
    CustomerOrderRepository,
)
from backend.infrastructure.db.repositories.orders_delivery.delivery_job_repository import (
    DeliveryJobRepository,
)
from backend.infrastructure.db.schema.orders_delivery_schema import (
    create_orders_delivery_schema,
)
from backend.shared.ids import new_uuid
from tests.integration._audit_trail_table import create_audit_logs_table

SUCURSAL = new_uuid()
OTRA_SUCURSAL = new_uuid()
USUARIO = new_uuid()
REPARTIDOR = new_uuid()
MOTIVO = "CUSTOMER_NOT_HOME"

ESPERADO = {
    DeliveryWorklist.PENDING_DRIVER_ASSIGNMENT: {"pendiente"},
    DeliveryWorklist.ACTIVE_DELIVERIES: {"despachado", "en_transito", "llego", "intento"},
    DeliveryWorklist.FAILED_DELIVERIES: {"fallido"},
    DeliveryWorklist.RETURNED_TO_BRANCH: {"devuelto"},
}

RUTA_A_BANDEJA = {
    "orders_driver_assignment": DeliveryWorklist.PENDING_DRIVER_ASSIGNMENT,
    "orders_active_deliveries": DeliveryWorklist.ACTIVE_DELIVERIES,
    "orders_failed_deliveries": DeliveryWorklist.FAILED_DELIVERIES,
    "orders_returns": DeliveryWorklist.RETURNED_TO_BRANCH,
}

#: Estados del trabajo que NO pertenecen a ninguna bandeja: si alguno aparece en
#: una, el filtro está de más.
FUERA_DE_BANDEJA = ("asignado", "listo", "entregado", "reentrega")


@pytest.fixture
def conn():
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    create_orders_delivery_schema(c)
    create_audit_logs_table(c)
    c.commit()
    yield c
    c.close()


@pytest.fixture(scope="module")
def app():
    qt = pytest.importorskip("PyQt5.QtWidgets")
    yield qt.QApplication.instance() or qt.QApplication([])


# -- siembra por dominio ----------------------------------------------------
def _pedido(etiqueta, *, branch_id):
    pedido = CustomerOrder.create(
        branch_id=branch_id, channel=OrderChannel.POS, order_type=OrderType.STANDARD,
        fulfillment_type=FulfillmentType.HOME_DELIVERY, operation_id=new_uuid(),
        contact_name=etiqueta)
    linea = CustomerOrderLine.create(
        order_id=pedido.id, product_id=new_uuid(), unit_price=Decimal("50"),
        requested_quantity=OrderQuantity(Decimal("2")))
    pedido.add_line(linea)
    return pedido, linea


def _pedido_despachado(etiqueta, *, branch_id):
    """El pedido tal como lo deja el despacho real: `DISPATCHED`. Un intento
    fallido posterior no lo cambia; por eso el badge viejo lo seguía contando
    como entrega activa."""
    pedido, linea = _pedido(etiqueta, branch_id=branch_id)
    pedido.confirm(confirmed_by_user_id=USUARIO)
    pedido.mark_reserved()
    pedido.assign_preparation(assigned_to_user_id=USUARIO)
    pedido.start_preparation()
    linea.record_prepared_amount(quantity=OrderQuantity(Decimal("2")))
    pedido.complete_preparation()
    pedido.mark_dispatched()
    return pedido


def _reserva_fallida(etiqueta, *, branch_id):
    """Pedido sin trabajo de reparto cuya reserva de inventario falló: el único
    escritor de `fulfillment_status=FAILED`."""
    pedido, _ = _pedido(etiqueta, branch_id=branch_id)
    pedido.confirm(confirmed_by_user_id=USUARIO)
    pedido.mark_reservation_failed()
    return pedido


def _llevar(trabajo, estado):
    """Lleva un trabajo por la tabla de transiciones hasta `estado`."""
    if estado == "pendiente":
        return
    trabajo.assign_driver(driver_id=REPARTIDOR)
    if estado == "asignado":
        return
    trabajo.mark_ready_to_dispatch()
    if estado == "listo":
        return
    trabajo.dispatch()
    if estado == "despachado":
        return
    trabajo.mark_in_transit()
    if estado == "en_transito":
        return
    trabajo.mark_arrived()
    if estado == "llego":
        return
    trabajo.start_delivery_attempt()
    if estado == "intento":
        return
    if estado == "entregado":
        trabajo.record_attempt(DeliveryAttempt.create(
            delivery_job_id=trabajo.id, successful=True,
            evidence=DeliveryEvidence(recipient_name="Juan", pin_verified=True)))
        return
    trabajo.record_attempt(DeliveryAttempt.create(
        delivery_job_id=trabajo.id, successful=False, failure_reason=MOTIVO))
    if estado == "fallido":
        return
    if estado == "reentrega":
        trabajo.request_redelivery()
        return
    if estado == "devuelto":
        trabajo.start_return()
        trabajo.complete_return()
        return
    raise ValueError(estado)


_ESTADOS_SEMBRADOS = ("pendiente", "asignado", "listo", "despachado", "en_transito",
                      "llego", "intento", "entregado", "fallido", "reentrega", "devuelto")


def _sembrar(conn, branch_id=SUCURSAL):
    pedidos = CustomerOrderRepository(conn)
    trabajos = DeliveryJobRepository(conn)
    for estado in _ESTADOS_SEMBRADOS:
        if estado == "fallido":
            pedido = _pedido_despachado(estado, branch_id=branch_id)
        else:
            pedido, _ = _pedido(estado, branch_id=branch_id)
        pedidos.save(pedido)
        trabajo = DeliveryJob.create(order_id=pedido.id, branch_id=branch_id,
                                     operation_id=new_uuid())
        _llevar(trabajo, estado)
        trabajos.save(trabajo)
    for etiqueta in ("reserva_fallida_1", "reserva_fallida_2"):
        pedidos.save(_reserva_fallida(etiqueta, branch_id=branch_id))
    conn.commit()


def _bandeja(conn, worklist, *, branch_id=SUCURSAL, **kwargs):
    pagina = DeliveryJobsWorklistQueryService(conn).list_worklist(branch_id, worklist, **kwargs)
    return {fila.contact_name for fila in pagina.rows}, pagina.total


# -- cada bandeja, su conjunto ----------------------------------------------
def test_every_worklist_has_an_expectation():
    assert set(ESPERADO) == set(DeliveryWorklist)


@pytest.mark.parametrize("worklist", sorted(DeliveryWorklist, key=lambda w: w.value))
def test_the_worklist_returns_exactly_its_jobs(conn, worklist):
    _sembrar(conn)

    nombres, total = _bandeja(conn, worklist)

    assert nombres == ESPERADO[worklist]
    assert total == len(ESPERADO[worklist])


def test_states_outside_every_worklist_appear_in_none(conn):
    """Asignado, listo, entregado y en reentrega no son de ninguna bandeja de
    este conjunto; un filtro que los incluyera estaría de más."""
    _sembrar(conn)
    for worklist in DeliveryWorklist:
        assert not (_bandeja(conn, worklist)[0] & set(FUERA_DE_BANDEJA)), worklist


def test_no_two_worklists_return_the_same_jobs(conn):
    _sembrar(conn)
    resultados = {w: _bandeja(conn, w)[0] for w in DeliveryWorklist}
    iguales = [(a.value, b.value) for a, b in combinations(DeliveryWorklist, 2)
               if resultados[a] == resultados[b]]
    assert not iguales, iguales


def test_another_branch_never_leaks_into_a_worklist(conn):
    """Aislamiento y sólo aislamiento: antes y después de sembrar otra sucursal."""
    _sembrar(conn)
    antes = {w: _bandeja(conn, w) for w in DeliveryWorklist}

    _sembrar(conn, branch_id=OTRA_SUCURSAL)
    despues = {w: _bandeja(conn, w) for w in DeliveryWorklist}

    assert despues == antes


def test_search_stays_inside_the_worklist(conn):
    _sembrar(conn)

    assert _bandeja(conn, DeliveryWorklist.ACTIVE_DELIVERIES, query="llego")[0] == {"llego"}
    assert _bandeja(conn, DeliveryWorklist.FAILED_DELIVERIES, query="llego")[0] == set()


def test_a_failed_job_shows_its_last_failure_reason(conn):
    _sembrar(conn)

    pagina = DeliveryJobsWorklistQueryService(conn).list_worklist(
        SUCURSAL, DeliveryWorklist.FAILED_DELIVERIES)

    assert [fila.last_failure_reason for fila in pagina.rows] == [MOTIVO]


# -- los dos badges corregidos --------------------------------------------------
@pytest.mark.parametrize("worklist", (DeliveryWorklist.ACTIVE_DELIVERIES,
                                      DeliveryWorklist.FAILED_DELIVERIES),
                         ids=lambda w: w.value)
def test_the_badge_counts_what_the_list_shows(conn, worklist):
    _sembrar(conn)

    badge = OrdersDeliveryBadgeQueryService(conn).get_badge_counts(SUCURSAL)[worklist.value]

    assert badge == _bandeja(conn, worklist)[1] == len(ESPERADO[worklist])


def test_a_failed_inventory_reservation_is_not_a_failed_delivery(conn):
    """FALLO #4. Dos reservas fallidas sin trabajo: el badge viejo contaba 2."""
    _sembrar(conn)

    assert OrdersDeliveryBadgeQueryService(conn).get_badge_counts(SUCURSAL)[
        DeliveryWorklist.FAILED_DELIVERIES.value] == 1


def test_a_failed_delivery_is_not_still_active(conn):
    """FALLO #5. El trabajo fallido deja su pedido en DISPATCHED; el badge viejo
    lo contaba como entrega activa (y sólo a él: los demás pedidos no llegan a
    DISPATCHED en la siembra)."""
    _sembrar(conn)

    activas = OrdersDeliveryBadgeQueryService(conn).get_badge_counts(SUCURSAL)[
        DeliveryWorklist.ACTIVE_DELIVERIES.value]
    assert activas == 4
    assert "fallido" not in _bandeja(conn, DeliveryWorklist.ACTIVE_DELIVERIES)[0]


# -- las pantallas ------------------------------------------------------------
def test_the_route_registry_matches_the_specification():
    from frontend.desktop.modules.orders_delivery import orders_delivery_routes as rutas

    con_bandeja = {ruta for ruta, builder in rutas._REAL_ROUTE_BUILDERS.items()
                   if builder == "_build_delivery_worklist"}
    assert con_bandeja == set(rutas._DELIVERY_WORKLIST_BY_ROUTE) == set(RUTA_A_BANDEJA)
    for ruta, (nombre, _vacio) in rutas._DELIVERY_WORKLIST_BY_ROUTE.items():
        assert DeliveryWorklist[nombre] is RUTA_A_BANDEJA[ruta], ruta


@pytest.mark.parametrize("ruta", sorted(RUTA_A_BANDEJA))
def test_the_route_opens_its_own_worklist(app, conn, ruta):
    from frontend.desktop.modules.orders_delivery.orders_delivery_routes import (
        ORDERS_DELIVERY_ROUTES,
        build_page,
    )
    from frontend.desktop.modules.orders_delivery.pages.delivery_job_worklist_page import (
        DeliveryJobWorklistPage,
    )

    _sembrar(conn)
    pagina = build_page(ruta, conn, branch_id=SUCURSAL, actor_user_id=USUARIO)

    assert isinstance(pagina, DeliveryJobWorklistPage)
    assert pagina.title == ORDERS_DELIVERY_ROUTES[ruta].title
    pagina.ensure_loaded()
    nombres = {pagina.table.item(fila, 2).text() for fila in range(pagina.table.rowCount())}
    assert nombres == ESPERADO[RUTA_A_BANDEJA[ruta]]


def test_the_failed_deliveries_page_shows_the_reason(app, conn):
    from frontend.desktop.modules.orders_delivery.orders_delivery_routes import build_page

    _sembrar(conn)
    pagina = build_page("orders_failed_deliveries", conn, branch_id=SUCURSAL,
                        actor_user_id=USUARIO)
    pagina.ensure_loaded()

    assert pagina.table.item(0, 5).text() == MOTIVO


def test_an_empty_worklist_shows_its_empty_state(app, conn):
    from frontend.desktop.modules.orders_delivery.orders_delivery_routes import build_page

    pagina = build_page("orders_returns", conn, branch_id=SUCURSAL, actor_user_id=USUARIO)
    pagina.ensure_loaded()

    assert pagina.table.rowCount() == 0
    assert pagina._stack.currentWidget() is pagina._empty
