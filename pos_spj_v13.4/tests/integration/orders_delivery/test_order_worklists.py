"""Bandejas de pedidos (PASS 6): cada una enseña lo suyo, y su badge cuenta lo mismo.

CÓMO SE SIEMBRA, Y POR QUÉ ASÍ
-------------------------------
Cada pedido se lleva a su estado CONDUCIENDO el dominio —`confirm()`,
`mark_reserved()`, `propose_substitution()`, `schedule()`…— y se guarda con
`CustomerOrderRepository`. No se insertan filas a mano: tres badges estaban mal
precisamente porque su SQL describía estados que el dominio no escribe. Sembrar
con SQL habría probado el filtro contra la misma suposición equivocada.

LO QUE SE FIJA
--------------
- Cada bandeja devuelve EXACTAMENTE su conjunto, y ninguna devuelve el de otra:
  en Transferencias cinco rutas enseñaban la misma lista con otro título.
- El badge cuenta lo mismo que la lista: comparten definición, y si divergieran
  el contador diría una cosa y la pantalla otra.
- Los tres fallos de badge corregidos, cada uno con su prueba con nombre propio.
"""
from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from itertools import combinations

import pytest

from backend.application.orders_delivery.queries.order_badge_query_service import (
    OrdersDeliveryBadgeQueryService,
)
from backend.application.orders_delivery.queries.order_worklists import OrderWorklist
from backend.application.orders_delivery.queries.orders_list_query_service import (
    OrdersListQueryService,
)
from backend.domain.orders_delivery.entities import CustomerOrder, CustomerOrderLine
from backend.domain.orders_delivery.enums import (
    FulfillmentType,
    OrderChannel,
    OrderType,
    SubstitutionType,
)
from backend.domain.orders_delivery.policies.catch_weight_adjustment_policy import (
    CatchWeightAdjustmentPolicy,
)
from backend.domain.orders_delivery.value_objects.order_quantity import OrderQuantity
from backend.infrastructure.db.repositories.orders_delivery.customer_order_repository import (
    CustomerOrderRepository,
)
from backend.infrastructure.db.schema.orders_delivery_schema import (
    create_orders_delivery_schema,
)
from backend.shared.ids import new_uuid

SUCURSAL = new_uuid()
OTRA_SUCURSAL = new_uuid()
USUARIO = new_uuid()
AHORA = datetime.now(timezone.utc)

#: Lo que cada bandeja tiene que devolver con la siembra de `_sembrar`.
ESPERADO = {
    OrderWorklist.SCHEDULED_PENDING_ACTIVATION: {"programado"},
    OrderWorklist.PENDING_CONFIRMATION: {"borrador", "activado"},
    OrderWorklist.PREPARATION_QUEUE: {"reservado", "preparando", "peso", "sustitucion"},
    OrderWorklist.WEIGHT_ADJUSTMENTS_PENDING: {"peso"},
    OrderWorklist.READY_FOR_PICKUP: {"listo_recoger"},
    OrderWorklist.READY_FOR_DISPATCH: {"listo_despacho"},
}

#: Qué ruta del sidebar abre qué bandeja. Escrito aquí a propósito, no leído del
#: registro de rutas: es la especificación contra la que se compara ese registro.
RUTA_A_BANDEJA = {
    "orders_scheduled": OrderWorklist.SCHEDULED_PENDING_ACTIVATION,
    "orders_pending_confirmation": OrderWorklist.PENDING_CONFIRMATION,
    "orders_preparation": OrderWorklist.PREPARATION_QUEUE,
    "orders_weight_adjustments": OrderWorklist.WEIGHT_ADJUSTMENTS_PENDING,
    "orders_ready_pickup": OrderWorklist.READY_FOR_PICKUP,
    "orders_ready_dispatch": OrderWorklist.READY_FOR_DISPATCH,
}

#: Badges que comparten definición con su bandeja.
BADGES_COMPARTIDOS = (
    OrderWorklist.SCHEDULED_PENDING_ACTIVATION,
    OrderWorklist.PENDING_CONFIRMATION,
    OrderWorklist.PREPARATION_QUEUE,
    OrderWorklist.WEIGHT_ADJUSTMENTS_PENDING,
)


@pytest.fixture
def conn():
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    create_orders_delivery_schema(c)
    c.commit()
    yield c
    c.close()


@pytest.fixture(scope="module")
def app():
    qt = pytest.importorskip("PyQt5.QtWidgets")
    yield qt.QApplication.instance() or qt.QApplication([])


# -- siembra por dominio ----------------------------------------------------
def _iso(momento: datetime) -> str:
    return momento.isoformat(timespec="seconds")


def _pedido(etiqueta, *, branch_id, tipo=FulfillmentType.PICKUP, peso=False):
    pedido = CustomerOrder.create(
        branch_id=branch_id, channel=OrderChannel.POS, order_type=OrderType.STANDARD,
        fulfillment_type=tipo, operation_id=new_uuid(), contact_name=etiqueta)
    if peso:
        linea = CustomerOrderLine.create(
            order_id=pedido.id, product_id=new_uuid(), unit_price=Decimal("100"),
            requested_weight=OrderQuantity(Decimal("1.000"), "KG"), catch_weight_enabled=True)
    else:
        linea = CustomerOrderLine.create(
            order_id=pedido.id, product_id=new_uuid(), unit_price=Decimal("50"),
            requested_quantity=OrderQuantity(Decimal("2")))
    pedido.add_line(linea)
    return pedido, linea


def _reservar(pedido):
    pedido.confirm(confirmed_by_user_id=USUARIO)
    pedido.mark_reserved()


def _empezar_preparacion(pedido):
    _reservar(pedido)
    pedido.assign_preparation(assigned_to_user_id=USUARIO)
    pedido.start_preparation()


def _dejar_listo(pedido, linea):
    _empezar_preparacion(pedido)
    linea.record_prepared_amount(quantity=OrderQuantity(Decimal("2")))
    pedido.complete_preparation()


def _programar(pedido, *, activacion):
    pedido.schedule(
        scheduled_for=_iso(AHORA + timedelta(days=1)),
        window_start=_iso(AHORA + timedelta(days=1)),
        window_end=_iso(AHORA + timedelta(days=1, hours=2)),
        activation_at=_iso(activacion))


def _sembrar(conn, branch_id=SUCURSAL) -> dict[str, str]:
    pedidos = []

    borrador, _ = _pedido("borrador", branch_id=branch_id)
    pedidos.append(borrador)

    programado, _ = _pedido("programado", branch_id=branch_id,
                            tipo=FulfillmentType.SCHEDULED_DELIVERY)
    _programar(programado, activacion=AHORA + timedelta(hours=5))
    pedidos.append(programado)

    activado, _ = _pedido("activado", branch_id=branch_id,
                          tipo=FulfillmentType.SCHEDULED_DELIVERY)
    _programar(activado, activacion=AHORA - timedelta(minutes=1))
    activado.activate_schedule(now=AHORA)
    pedidos.append(activado)

    reservado, _ = _pedido("reservado", branch_id=branch_id)
    _reservar(reservado)
    pedidos.append(reservado)

    preparando, _ = _pedido("preparando", branch_id=branch_id)
    _empezar_preparacion(preparando)
    pedidos.append(preparando)

    peso, linea_peso = _pedido("peso", branch_id=branch_id, peso=True)
    _empezar_preparacion(peso)
    linea_peso.record_prepared_amount(weight=OrderQuantity(Decimal("1.500"), "KG"))
    peso.apply_weight_evaluation(
        line_id=linea_peso.id,
        evaluation=CatchWeightAdjustmentPolicy.evaluate(
            requested_amount=Decimal("1.000"), prepared_amount=Decimal("1.500"),
            unit_price=Decimal("100"), tolerance_pct=Decimal("5")))
    pedidos.append(peso)

    sustitucion, linea_sus = _pedido("sustitucion", branch_id=branch_id)
    _reservar(sustitucion)
    sustitucion.propose_substitution(
        line_id=linea_sus.id, substitute_product_id=new_uuid(),
        substitution_type=SubstitutionType.EQUIVALENT_PRODUCT,
        new_unit_price=Decimal("55"), reason="Sin existencia")
    pedidos.append(sustitucion)

    recoger, linea_rec = _pedido("listo_recoger", branch_id=branch_id)
    _dejar_listo(recoger, linea_rec)
    pedidos.append(recoger)

    despacho, linea_desp = _pedido("listo_despacho", branch_id=branch_id,
                                   tipo=FulfillmentType.HOME_DELIVERY)
    _dejar_listo(despacho, linea_desp)
    pedidos.append(despacho)

    despachado, linea_ya = _pedido("despachado", branch_id=branch_id,
                                   tipo=FulfillmentType.HOME_DELIVERY)
    _dejar_listo(despachado, linea_ya)
    despachado.mark_dispatched()
    pedidos.append(despachado)

    repositorio = CustomerOrderRepository(conn)
    for pedido in pedidos:
        repositorio.save(pedido)
    conn.commit()
    return {pedido.contact_name: pedido.id for pedido in pedidos}


def _bandeja(conn, worklist, *, branch_id=SUCURSAL, **kwargs):
    pagina = OrdersListQueryService(conn).list_worklist(branch_id, worklist, **kwargs)
    return {fila.contact_name for fila in pagina.rows}, pagina.total


# -- cada bandeja, su conjunto ----------------------------------------------
def test_every_worklist_has_an_expectation():
    """Una bandeja nueva sin expectativa pasaría sin probarse."""
    assert set(ESPERADO) == set(OrderWorklist)


@pytest.mark.parametrize("worklist", sorted(OrderWorklist, key=lambda w: w.value))
def test_the_worklist_returns_exactly_its_orders(conn, worklist):
    _sembrar(conn)

    nombres, total = _bandeja(conn, worklist)

    assert nombres == ESPERADO[worklist]
    assert total == len(ESPERADO[worklist])


def test_no_two_worklists_return_the_same_orders(conn):
    """La lección de Transferencias: rutas distintas con el mismo contenido."""
    _sembrar(conn)
    resultados = {w: _bandeja(conn, w)[0] for w in OrderWorklist}

    iguales = [(a.value, b.value) for a, b in combinations(OrderWorklist, 2)
               if resultados[a] == resultados[b]]
    assert not iguales, f"Bandejas con el mismo contenido: {iguales}"


def test_another_branch_never_leaks_into_a_worklist(conn):
    """Aislamiento, y SOLO aislamiento: se compara cada bandeja antes y después
    de sembrar otra sucursal con los mismos estados.

    La primera versión comparaba el total contra `ESPERADO`, y por eso caía ante
    CUALQUIER filtro mutado —se vio al correr las mutaciones— sin decir nada de
    la sucursal. Así sólo falla si la otra sucursal se cuela.
    """
    _sembrar(conn)
    antes = {worklist: _bandeja(conn, worklist) for worklist in OrderWorklist}

    _sembrar(conn, branch_id=OTRA_SUCURSAL)
    despues = {worklist: _bandeja(conn, worklist) for worklist in OrderWorklist}

    assert despues == antes


def test_search_stays_inside_the_worklist(conn):
    _sembrar(conn)

    assert _bandeja(conn, OrderWorklist.PREPARATION_QUEUE, query="peso")[0] == {"peso"}
    assert _bandeja(conn, OrderWorklist.READY_FOR_PICKUP, query="peso")[0] == set()


# -- badge == lista ---------------------------------------------------------
@pytest.mark.parametrize("worklist", BADGES_COMPARTIDOS, ids=lambda w: w.value)
def test_the_badge_counts_what_the_list_shows(conn, worklist):
    _sembrar(conn)

    badge = OrdersDeliveryBadgeQueryService(conn).get_badge_counts(SUCURSAL)[worklist.value]

    assert badge == _bandeja(conn, worklist)[1] == len(ESPERADO[worklist])


# -- los tres fallos de badge, con nombre propio ------------------------------
def test_a_reserved_order_waits_in_the_preparation_queue(conn):
    """FALLO 1. `assign_preparation()` exige `RESERVED`; el badge lo excluía."""
    _sembrar(conn)

    assert "reservado" in _bandeja(conn, OrderWorklist.PREPARATION_QUEUE)[0]
    assert "borrador" not in _bandeja(conn, OrderWorklist.PREPARATION_QUEUE)[0]


def test_a_pending_substitution_is_not_a_weight_adjustment(conn):
    """FALLO 2. Peso y sustitución comparten la aprobación del cliente; sólo la
    sustitución rellena `substitute_product_id`."""
    _sembrar(conn)

    assert _bandeja(conn, OrderWorklist.WEIGHT_ADJUSTMENTS_PENDING)[0] == {"peso"}


def test_scheduling_is_read_from_schedule_status_not_order_type(conn):
    """FALLO 3. `schedule()` no toca `order_type` ni `status`: el badge se
    saltaba los programados y contaba los ya activados."""
    _sembrar(conn)

    programados = _bandeja(conn, OrderWorklist.SCHEDULED_PENDING_ACTIVATION)[0]
    assert "programado" in programados
    assert "activado" not in programados


def test_a_cancelled_ready_order_is_no_longer_ready(conn):
    """Un pedido cancelado conserva `fulfillment_status=READY`; no puede salir en
    "Listos para recoger". Se cancela con UPDATE porque lo que se prueba es el
    filtro, no el caso de uso de cancelación."""
    ids = _sembrar(conn)
    conn.execute("UPDATE customer_orders SET status='CANCELLED' WHERE id=?",
                 (ids["listo_recoger"],))
    conn.commit()

    assert _bandeja(conn, OrderWorklist.READY_FOR_PICKUP)[0] == set()


# -- las pantallas ------------------------------------------------------------
def test_the_route_registry_matches_the_specification():
    from frontend.desktop.modules.orders_delivery import orders_delivery_routes as rutas

    con_bandeja = {ruta for ruta, builder in rutas._REAL_ROUTE_BUILDERS.items()
                   if builder == "_build_order_worklist"}
    assert con_bandeja == set(rutas._WORKLIST_BY_ROUTE) == set(RUTA_A_BANDEJA)
    for ruta, (nombre, _vacio) in rutas._WORKLIST_BY_ROUTE.items():
        assert OrderWorklist[nombre] is RUTA_A_BANDEJA[ruta], ruta


@pytest.mark.parametrize("ruta", sorted(RUTA_A_BANDEJA))
def test_the_route_opens_its_own_worklist(app, conn, ruta):
    from frontend.desktop.modules.orders_delivery.orders_delivery_routes import (
        ORDERS_DELIVERY_ROUTES,
        build_page,
    )
    from frontend.desktop.modules.orders_delivery.pages.order_worklist_page import (
        OrderWorklistPage,
    )

    _sembrar(conn)
    pagina = build_page(ruta, conn, branch_id=SUCURSAL, actor_user_id=USUARIO)

    assert isinstance(pagina, OrderWorklistPage)
    assert pagina.title == ORDERS_DELIVERY_ROUTES[ruta].title
    pagina.ensure_loaded()
    nombres = {pagina.table.item(fila, 5).text() for fila in range(pagina.table.rowCount())}
    assert nombres == ESPERADO[RUTA_A_BANDEJA[ruta]]


def test_an_empty_worklist_shows_its_empty_state(app, conn):
    from frontend.desktop.modules.orders_delivery.orders_delivery_routes import build_page

    pagina = build_page("orders_ready_pickup", conn, branch_id=SUCURSAL, actor_user_id=USUARIO)
    pagina.ensure_loaded()

    assert pagina.table.rowCount() == 0
    assert pagina._stack.currentWidget() is pagina._empty
