"""Registros de reparto (PASS 6): reentregas, cobros en ruta, liquidaciones y rutas.

No son bandejas: enseñan todo lo de la sucursal, con filtro por estado, y ponen
primero lo que pide atención. Lo que se fija aquí:

- Cada registro devuelve todo lo suyo y sólo lo suyo. Reentregas y cobros NO tienen
  `branch_id`: su sucursal es la del trabajo de reparto. Sin ese JOIN la lista
  enseñaría los de todas las sucursales y parecería funcionar.
- Lo que pide atención va arriba; el filtro por estado devuelve sólo ese estado, y
  un estado inventado se rechaza en vez de dar una lista vacía que parece real.
- El badge de liquidaciones cuenta lo mismo que la lista filtrada por "En revisión".

Como en las bandejas, todo se siembra CONDUCIENDO el dominio —`request_redelivery`,
`record_collection`, `DriverSettlement.create`, `plan`…— y guardando con el
repositorio de cada agregado.
"""
from __future__ import annotations

import sqlite3
from decimal import Decimal

import pytest

from backend.application.orders_delivery.queries.delivery_records_query_service import (
    SEARCHABLE_RECORDS,
    STATUS_ENUM,
    DeliveryRecord,
    DeliveryRecordsQueryService,
)
from backend.application.orders_delivery.queries.order_badge_query_service import (
    OrdersDeliveryBadgeQueryService,
)
from backend.domain.orders_delivery.cash_collection import DriverCashCollection
from backend.domain.orders_delivery.delivery_job import DeliveryAttempt, DeliveryJob
from backend.domain.orders_delivery.entities import CustomerOrder, CustomerOrderLine
from backend.domain.orders_delivery.enums import (
    CollectionPaymentMethod,
    FulfillmentType,
    OrderChannel,
    OrderType,
)
from backend.domain.orders_delivery.redelivery import RedeliveryRequest
from backend.domain.orders_delivery.route import DeliveryRoute
from backend.domain.orders_delivery.settlement import DriverSettlement
from backend.domain.orders_delivery.value_objects.order_quantity import OrderQuantity
from backend.infrastructure.db.repositories.orders_delivery.cash_collection_repository import (
    DriverCashCollectionRepository,
)
from backend.infrastructure.db.repositories.orders_delivery.customer_order_repository import (
    CustomerOrderRepository,
)
from backend.infrastructure.db.repositories.orders_delivery.delivery_job_repository import (
    DeliveryJobRepository,
)
from backend.infrastructure.db.repositories.orders_delivery.redelivery_repository import (
    RedeliveryRequestRepository,
)
from backend.infrastructure.db.repositories.orders_delivery.route_repository import (
    DeliveryRouteRepository,
)
from backend.infrastructure.db.repositories.orders_delivery.settlement_repository import (
    DriverSettlementRepository,
)
from backend.infrastructure.db.schema.orders_delivery_schema import (
    create_orders_delivery_schema,
)
from backend.shared.ids import new_uuid
from frontend.desktop.modules.orders_delivery.presenters.delivery_record_presenter import (
    PAYMENT_METHOD_LABELS,
    STATUS_LABELS,
    DeliveryRecordPresenter,
)

SUCURSAL = new_uuid()
OTRA_SUCURSAL = new_uuid()
USUARIO = new_uuid()
REPARTIDOR = new_uuid()

RUTA_A_REGISTRO = {
    "orders_routes": DeliveryRecord.ROUTES,
    "orders_redeliveries": DeliveryRecord.REDELIVERIES,
    "orders_cash_collections": DeliveryRecord.CASH_COLLECTIONS,
    "orders_settlements": DeliveryRecord.SETTLEMENTS,
}

#: Estados sembrados por registro (uno de cada), y cuáles NO piden atención y por
#: tanto van al final.
SEMBRADOS = {
    DeliveryRecord.REDELIVERIES: {"PENDING", "APPROVED", "REJECTED"},
    DeliveryRecord.CASH_COLLECTIONS: {"EXPECTED", "COLLECTED", "PARTIALLY_COLLECTED", "FAILED"},
    DeliveryRecord.SETTLEMENTS: {"BALANCED", "PENDING_REVIEW", "WITH_DIFFERENCE", "CLOSED"},
    DeliveryRecord.ROUTES: {"DRAFT", "PLANNED", "COMPLETED", "CANCELLED"},
}
AL_FINAL = {
    DeliveryRecord.REDELIVERIES: {"APPROVED", "REJECTED"},
    DeliveryRecord.CASH_COLLECTIONS: {"COLLECTED"},
    DeliveryRecord.SETTLEMENTS: {"CLOSED"},
    DeliveryRecord.ROUTES: {"COMPLETED", "CANCELLED"},
}


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
def _trabajo(conn, etiqueta, *, branch_id, fallido=False, cobrar=Decimal("0")):
    pedido = CustomerOrder.create(
        branch_id=branch_id, channel=OrderChannel.POS, order_type=OrderType.STANDARD,
        fulfillment_type=FulfillmentType.HOME_DELIVERY, operation_id=new_uuid(),
        contact_name=etiqueta)
    pedido.add_line(CustomerOrderLine.create(
        order_id=pedido.id, product_id=new_uuid(), unit_price=Decimal("50"),
        requested_quantity=OrderQuantity(Decimal("2"))))
    CustomerOrderRepository(conn).save(pedido)
    trabajo = DeliveryJob.create(order_id=pedido.id, branch_id=branch_id,
                                 operation_id=new_uuid(), cash_to_collect=cobrar)
    trabajo.assign_driver(driver_id=REPARTIDOR)
    if fallido:
        trabajo.mark_ready_to_dispatch()
        trabajo.dispatch()
        trabajo.mark_in_transit()
        trabajo.mark_arrived()
        trabajo.start_delivery_attempt()
        trabajo.record_attempt(DeliveryAttempt.create(
            delivery_job_id=trabajo.id, successful=False, failure_reason="CUSTOMER_NOT_HOME"))
    DeliveryJobRepository(conn).save(trabajo)
    return trabajo


def _sembrar_reentregas(conn, branch_id):
    """Como `RequestRedeliveryUseCase` y `ApproveRedeliveryUseCase`: la solicitud
    sale de un trabajo FALLIDO, y aprobarla crea un trabajo NUEVO."""
    trabajos = DeliveryJobRepository(conn)
    solicitudes = RedeliveryRequestRepository(conn)
    for etiqueta in ("pendiente", "aprobada", "rechazada"):
        trabajo = _trabajo(conn, etiqueta, branch_id=branch_id, fallido=True)
        solicitud = RedeliveryRequest.create(
            original_delivery_job_id=trabajo.id, reason=f"Cliente ausente {etiqueta}",
            requested_by_user_id=USUARIO, additional_fee=Decimal("35"))
        trabajo.request_redelivery()
        trabajos.save(trabajo)
        if etiqueta == "aprobada":
            nuevo = DeliveryJob.create(order_id=trabajo.order_id, branch_id=branch_id,
                                       operation_id=new_uuid())
            trabajos.save(nuevo)
            solicitud.approve(approved_by_user_id=USUARIO, new_delivery_job_id=nuevo.id)
        elif etiqueta == "rechazada":
            solicitud.reject()
        solicitudes.save(solicitud)


#: Cobro esperado de 150; lo cobrado decide el estado (`record_collection`).
_COBROS = {"por_cobrar": None, "cobrado": Decimal("150"), "parcial": Decimal("100"),
           "no_cobrado": Decimal("0")}


def _sembrar_cobros(conn, branch_id):
    cobros = DriverCashCollectionRepository(conn)
    for etiqueta, cobrado in _COBROS.items():
        trabajo = _trabajo(conn, etiqueta, branch_id=branch_id, cobrar=Decimal("150"))
        cobro = DriverCashCollection.create(
            delivery_job_id=trabajo.id, driver_id=REPARTIDOR,
            expected_amount=trabajo.cash_to_collect, payment_method=CollectionPaymentMethod.CASH)
        if cobrado is not None:
            cobro.record_collection(collected_amount=cobrado)
        cobros.save(cobro)


def _liquidacion(conn, *, branch_id, cobrado, avanzar=lambda s: None):
    """Como `CreateDriverSettlementUseCase`: concilia cobros por liquidar y los marca
    liquidados. Esperado siempre 100."""
    trabajo = _trabajo(conn, "liquidacion", branch_id=branch_id, cobrar=Decimal("100"))
    cobro = DriverCashCollection.create(
        delivery_job_id=trabajo.id, driver_id=REPARTIDOR, expected_amount=Decimal("100"),
        payment_method=CollectionPaymentMethod.CASH)
    cobro.record_collection(collected_amount=cobrado)
    cobro.mark_pending_settlement()
    liquidacion = DriverSettlement.create(
        driver_id=REPARTIDOR, branch_id=branch_id, collections=[cobro])
    cobro.mark_settled()
    DriverCashCollectionRepository(conn).save(cobro)
    avanzar(liquidacion)
    DriverSettlementRepository(conn).save(liquidacion)


def _cerrar(liquidacion):
    liquidacion.approve(approved_by_user_id=USUARIO)
    liquidacion.post()
    liquidacion.close()


def _sembrar_liquidaciones(conn, branch_id):
    _liquidacion(conn, branch_id=branch_id, cobrado=Decimal("100"))  # BALANCED
    _liquidacion(conn, branch_id=branch_id, cobrado=Decimal("80"),   # PENDING_REVIEW
                 avanzar=lambda s: s.submit_for_review(reviewed_by_user_id=USUARIO))
    _liquidacion(conn, branch_id=branch_id, cobrado=Decimal("120"))  # WITH_DIFFERENCE
    _liquidacion(conn, branch_id=branch_id, cobrado=Decimal("100"), avanzar=_cerrar)  # CLOSED


#: Paradas por estado de ruta.
PARADAS = {"DRAFT": "2", "PLANNED": "1", "COMPLETED": "1", "CANCELLED": "0"}


def _sembrar_rutas(conn, branch_id):
    def con_paradas(n):
        ruta = DeliveryRoute.create(branch_id=branch_id)
        for secuencia in range(1, n + 1):
            trabajo = _trabajo(conn, f"parada{secuencia}", branch_id=branch_id)
            ruta.add_stop(delivery_job_id=trabajo.id, sequence=secuencia)
        return ruta

    borrador = con_paradas(2)
    planificada = con_paradas(1)
    planificada.plan()
    completada = con_paradas(1)
    completada.plan()
    completada.assign_driver(driver_id=REPARTIDOR)
    completada.activate()
    completada.complete()
    cancelada = DeliveryRoute.create(branch_id=branch_id)
    cancelada.cancel()
    rutas = DeliveryRouteRepository(conn)
    for ruta in (borrador, planificada, completada, cancelada):
        rutas.save(ruta)


_SEMBRADORES = {
    DeliveryRecord.REDELIVERIES: _sembrar_reentregas,
    DeliveryRecord.CASH_COLLECTIONS: _sembrar_cobros,
    DeliveryRecord.SETTLEMENTS: _sembrar_liquidaciones,
    DeliveryRecord.ROUTES: _sembrar_rutas,
}


def _sembrar(conn, record, branch_id=SUCURSAL):
    _SEMBRADORES[record](conn, branch_id)
    conn.commit()


def _pagina(conn, record, **kwargs):
    return DeliveryRecordsQueryService(conn).list_records(SUCURSAL, record, **kwargs)


def _estados(pagina):
    return [fila["status"] for fila in pagina.rows]


_REGISTROS = sorted(DeliveryRecord, key=lambda r: r.value)


# -- lo que devuelve cada registro --------------------------------------------
@pytest.mark.parametrize("record", _REGISTROS, ids=lambda r: r.value)
def test_the_record_lists_everything_of_the_branch(conn, record):
    _sembrar(conn, record)

    pagina = _pagina(conn, record)

    assert sorted(_estados(pagina)) == sorted(SEMBRADOS[record])
    assert pagina.total == len(SEMBRADOS[record])


@pytest.mark.parametrize("record", _REGISTROS, ids=lambda r: r.value)
def test_what_needs_attention_comes_first(conn, record):
    _sembrar(conn, record)

    estados = _estados(_pagina(conn, record))
    primeros = len(SEMBRADOS[record]) - len(AL_FINAL[record])

    assert set(estados[primeros:]) == AL_FINAL[record], estados


@pytest.mark.parametrize("record", _REGISTROS, ids=lambda r: r.value)
def test_the_status_filter_returns_only_that_status(conn, record):
    _sembrar(conn, record)

    for estado in SEMBRADOS[record]:
        pagina = _pagina(conn, record, status=estado)
        assert _estados(pagina) == [estado]
        assert pagina.total == 1


@pytest.mark.parametrize("record", _REGISTROS, ids=lambda r: r.value)
def test_an_unknown_status_is_rejected_not_shown_as_empty(conn, record):
    with pytest.raises(ValueError):
        _pagina(conn, record, status="NO_EXISTE")


@pytest.mark.parametrize("record", _REGISTROS, ids=lambda r: r.value)
def test_another_branch_never_leaks_into_the_record(conn, record):
    """Aislamiento y sólo aislamiento: antes y después de sembrar otra sucursal."""
    _sembrar(conn, record)
    antes = _pagina(conn, record)

    _sembrar(conn, record, branch_id=OTRA_SUCURSAL)
    despues = _pagina(conn, record)

    assert (despues.rows, despues.total) == (antes.rows, antes.total)


def test_search_finds_redeliveries_and_collections_by_customer(conn):
    _sembrar(conn, DeliveryRecord.REDELIVERIES)
    _sembrar(conn, DeliveryRecord.CASH_COLLECTIONS)

    reentregas = _pagina(conn, DeliveryRecord.REDELIVERIES, query="rechazada")
    cobros = _pagina(conn, DeliveryRecord.CASH_COLLECTIONS, query="parcial")

    assert [f["contact_name"] for f in reentregas.rows] == ["rechazada"]
    assert [f["contact_name"] for f in cobros.rows] == ["parcial"]


@pytest.mark.parametrize("record", sorted(set(DeliveryRecord) - SEARCHABLE_RECORDS,
                                          key=lambda r: r.value), ids=lambda r: r.value)
def test_a_record_without_text_rejects_a_search(conn, record):
    with pytest.raises(ValueError):
        _pagina(conn, record, query="algo")


# -- formato ------------------------------------------------------------------------
def _filas(conn, record, **kwargs):
    return DeliveryRecordPresenter(conn, branch_id=SUCURSAL, record=record).rows(**kwargs).rows


def test_a_partial_collection_shows_expected_and_collected(conn):
    _sembrar(conn, DeliveryRecord.CASH_COLLECTIONS)

    [fila] = _filas(conn, DeliveryRecord.CASH_COLLECTIONS, status="PARTIALLY_COLLECTED")

    assert fila[2] == "parcial"
    assert fila[4:8] == ["Efectivo", "$150.00", "$100.00", "Cobro parcial"]


@pytest.mark.parametrize("estado, diferencia", [
    ("BALANCED", "$0.00"), ("PENDING_REVIEW", "-$20.00"), ("WITH_DIFFERENCE", "+$20.00")])
def test_a_settlement_shows_its_signed_difference(conn, estado, diferencia):
    _sembrar(conn, DeliveryRecord.SETTLEMENTS)

    [fila] = _filas(conn, DeliveryRecord.SETTLEMENTS, status=estado)

    assert fila[2] == "1"
    assert fila[5] == diferencia


def test_the_settlements_badge_counts_what_the_filtered_list_shows(conn):
    _sembrar(conn, DeliveryRecord.SETTLEMENTS)

    badge = OrdersDeliveryBadgeQueryService(conn).get_badge_counts(SUCURSAL)[
        "settlements_pending_review"]

    assert badge == _pagina(conn, DeliveryRecord.SETTLEMENTS, status="PENDING_REVIEW").total == 1


def test_a_route_shows_how_many_stops_it_has(conn):
    _sembrar(conn, DeliveryRecord.ROUTES)

    for estado, paradas in PARADAS.items():
        [fila] = _filas(conn, DeliveryRecord.ROUTES, status=estado)
        assert fila[3] == paradas, estado


@pytest.mark.parametrize("record", _REGISTROS, ids=lambda r: r.value)
def test_every_status_has_a_label(record):
    assert set(STATUS_LABELS[record]) == {estado.value for estado in STATUS_ENUM[record]}


def test_every_payment_method_has_a_label():
    assert set(PAYMENT_METHOD_LABELS) == {m.value for m in CollectionPaymentMethod}


# -- las pantallas ------------------------------------------------------------
def test_the_route_registry_matches_the_specification():
    from frontend.desktop.modules.orders_delivery import orders_delivery_routes as rutas

    con_registro = {ruta for ruta, builder in rutas._REAL_ROUTE_BUILDERS.items()
                    if builder == "_build_delivery_record"}
    assert con_registro == set(rutas._DELIVERY_RECORD_BY_ROUTE) == set(RUTA_A_REGISTRO)
    for ruta, (nombre, _vacio) in rutas._DELIVERY_RECORD_BY_ROUTE.items():
        assert DeliveryRecord[nombre] is RUTA_A_REGISTRO[ruta], ruta


@pytest.mark.parametrize("ruta", sorted(RUTA_A_REGISTRO))
def test_the_route_opens_its_own_record(app, conn, ruta):
    from frontend.desktop.modules.orders_delivery.orders_delivery_routes import (
        ORDERS_DELIVERY_ROUTES,
        build_page,
    )
    from frontend.desktop.modules.orders_delivery.pages.delivery_record_page import (
        DeliveryRecordPage,
    )

    record = RUTA_A_REGISTRO[ruta]
    _sembrar(conn, record)
    pagina = build_page(ruta, conn, branch_id=SUCURSAL, actor_user_id=USUARIO)

    assert isinstance(pagina, DeliveryRecordPage)
    assert pagina.title == ORDERS_DELIVERY_ROUTES[ruta].title
    assert {valor for valor, _ in pagina.status_filter} == {
        estado.value for estado in STATUS_ENUM[record]}
    pagina.ensure_loaded()
    # `reload()` se traga el error y lo pinta en el aviso: sin esta línea, una
    # fila con más columnas que la tabla pasaría por "no hay registros".
    assert pagina._notice.isHidden(), pagina._notice.text()
    assert pagina.table.rowCount() == len(SEMBRADOS[record])


def test_an_empty_record_shows_its_empty_state(app, conn):
    from frontend.desktop.modules.orders_delivery.orders_delivery_routes import build_page

    pagina = build_page("orders_settlements", conn, branch_id=SUCURSAL, actor_user_id=USUARIO)
    pagina.ensure_loaded()

    assert pagina._notice.isHidden(), pagina._notice.text()
    assert pagina.table.rowCount() == 0
    assert pagina._stack.currentWidget() is pagina._empty
