"""Registros de reparto (PASS 6): reentregas, cobros en ruta, liquidaciones, rutas,
seguimiento, incidencias, alertas y auditoría.

No son bandejas: enseñan todo lo de la sucursal, con filtro por estado, y ponen
primero lo que pide atención. Lo que se fija aquí:

- Cada registro devuelve todo lo suyo y sólo lo suyo. Reentregas, cobros e
  intentos NO tienen `branch_id`: su sucursal es la del trabajo de reparto. Sin
  ese JOIN la lista enseñaría los de todas las sucursales y parecería funcionar.
- Lo que pide atención va arriba; el filtro por estado devuelve sólo ese estado, y
  un estado inventado se rechaza en vez de dar una lista vacía que parece real.
- Seguimiento enseña el trabajo MÁS RECIENTE de cada pedido: tras una reentrega el
  trabajo viejo queda en REDELIVERY_PENDING para siempre.
- Alertas es por persona: la bandeja guarda un renglón por destinatario, y lo que
  lee un colega no marca la mía.
- Auditoría enseña lo que escribieron los CASOS DE USO; por eso se siembra
  llamándolos, no insertando renglones.

Como en las bandejas, todo se siembra CONDUCIENDO el dominio —`request_redelivery`,
`record_collection`, `DriverSettlement.create`, `plan`…— y guardando con el
repositorio de cada agregado. Las alertas las escribe el notificador real.
"""
from __future__ import annotations

import sqlite3
from decimal import Decimal

import pytest

from backend.application.orders_delivery.authorization import OrdersDeliveryAuthorizationPolicy
from backend.application.orders_delivery.permissions import ALL_ORDERS_DELIVERY_PERMISSIONS
from backend.application.orders_delivery.queries.delivery_records_query_service import (
    PER_RECIPIENT_RECORDS,
    SEARCHABLE_RECORDS,
    STATUS_ENUM,
    DeliveryRecord,
    DeliveryRecordsQueryService,
)
from backend.application.orders_delivery.queries.order_badge_query_service import (
    OrdersDeliveryBadgeQueryService,
)
from backend.application.orders_delivery.session_authorization import (
    OrdersDeliverySessionPermissionChecker,
)
from backend.application.orders_delivery.use_cases.order_capture_use_cases import (
    ConfirmCustomerOrderUseCase,
    CreateCustomerOrderUseCase,
)
from backend.application.orders_delivery.use_cases.zone_use_cases import (
    CreateDeliveryZoneUseCase,
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
from backend.domain.orders_delivery.value_objects.delivery_evidence import DeliveryEvidence
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
from backend.infrastructure.integrations.orders_delivery_internal_notifier import (
    OrdersDeliveryInternalNotifier,
)
from backend.shared.ids import new_uuid
from frontend.desktop.modules.orders_delivery.presenters.delivery_record_presenter import (
    PAYMENT_METHOD_LABELS,
    STATUS_LABELS,
    DeliveryRecordPresenter,
)
from tests.integration._born_clean_db import make_db
from tests.integration._audit_trail_table import create_audit_logs_table

SUCURSAL = new_uuid()
OTRA_SUCURSAL = new_uuid()
USUARIO = new_uuid()
REPARTIDOR = new_uuid()

RUTA_A_REGISTRO = {
    "orders_routes": DeliveryRecord.ROUTES,
    "orders_redeliveries": DeliveryRecord.REDELIVERIES,
    "orders_cash_collections": DeliveryRecord.CASH_COLLECTIONS,
    "orders_settlements": DeliveryRecord.SETTLEMENTS,
    "orders_tracking": DeliveryRecord.TRACKING,
    "orders_incidents": DeliveryRecord.INCIDENTS,
    "orders_alerts": DeliveryRecord.ALERTS,
    "orders_audit": DeliveryRecord.AUDIT,
}

#: Estados sembrados por registro (uno de cada), y cuáles NO piden atención y por
#: tanto van al final. En incidencias el "estado" es el motivo y nada pide atención.
SEMBRADOS = {
    DeliveryRecord.REDELIVERIES: {"PENDING", "APPROVED", "REJECTED"},
    DeliveryRecord.CASH_COLLECTIONS: {"EXPECTED", "COLLECTED", "PARTIALLY_COLLECTED", "FAILED"},
    DeliveryRecord.SETTLEMENTS: {"BALANCED", "PENDING_REVIEW", "WITH_DIFFERENCE", "CLOSED"},
    DeliveryRecord.ROUTES: {"DRAFT", "PLANNED", "COMPLETED", "CANCELLED"},
    DeliveryRecord.TRACKING: {"ASSIGNED", "IN_TRANSIT", "DELIVERED", "PENDING_ASSIGNMENT"},
    DeliveryRecord.INCIDENTS: {"CUSTOMER_NOT_HOME", "ADDRESS_NOT_FOUND", "VEHICLE_FAILURE"},
    DeliveryRecord.AUDIT: {"ORDER_CREATED", "ORDER_CONFIRMED", "DELIVERY_ZONE_CREATED"},
}
AL_FINAL = {
    DeliveryRecord.REDELIVERIES: {"APPROVED", "REJECTED"},
    DeliveryRecord.CASH_COLLECTIONS: {"COLLECTED"},
    DeliveryRecord.SETTLEMENTS: {"CLOSED"},
    DeliveryRecord.ROUTES: {"COMPLETED", "CANCELLED"},
    DeliveryRecord.TRACKING: {"DELIVERED"},
    DeliveryRecord.INCIDENTS: {"CUSTOMER_NOT_HOME", "ADDRESS_NOT_FOUND", "VEHICLE_FAILURE"},
    DeliveryRecord.AUDIT: {"ORDER_CREATED", "ORDER_CONFIRMED", "DELIVERY_ZONE_CREATED"},
}
#: Columna que hace de "estado" en cada registro.
_CLAVE_ESTADO = {DeliveryRecord.TRACKING: "job_status",
                 DeliveryRecord.INCIDENTS: "failure_reason",
                 DeliveryRecord.AUDIT: "action"}


@pytest.fixture
def conn():
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    create_orders_delivery_schema(c)
    create_audit_logs_table(c)
    c.commit()
    yield c
    c.close()


@pytest.fixture
def conn_completa():
    """Esquema canónico completo: alertas necesita usuarios, roles y la bandeja."""
    c = make_db()
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
def _pedido(conn, etiqueta, *, branch_id):
    pedido = CustomerOrder.create(
        branch_id=branch_id, channel=OrderChannel.POS, order_type=OrderType.STANDARD,
        fulfillment_type=FulfillmentType.HOME_DELIVERY, operation_id=new_uuid(),
        contact_name=etiqueta, contact_phone="5512345678")
    pedido.add_line(CustomerOrderLine.create(
        order_id=pedido.id, product_id=new_uuid(), unit_price=Decimal("50"),
        requested_quantity=OrderQuantity(Decimal("2"))))
    CustomerOrderRepository(conn).save(pedido)
    return pedido


def _trabajo(conn, etiqueta, *, branch_id, hasta="asignado", cobrar=Decimal("0"),
             motivo="CUSTOMER_NOT_HOME", order_id=None):
    """Un trabajo llevado por la tabla de transiciones hasta `hasta`:
    "pendiente", "asignado", "en_camino", "entregado" o "fallido"."""
    if order_id is None:
        order_id = _pedido(conn, etiqueta, branch_id=branch_id).id
    trabajo = DeliveryJob.create(order_id=order_id, branch_id=branch_id,
                                 operation_id=new_uuid(), cash_to_collect=cobrar)
    if hasta != "pendiente":
        trabajo.assign_driver(driver_id=REPARTIDOR)
    if hasta in ("en_camino", "entregado", "fallido"):
        trabajo.mark_ready_to_dispatch()
        trabajo.dispatch()
        trabajo.mark_in_transit()
    if hasta in ("entregado", "fallido"):
        trabajo.mark_arrived()
        trabajo.start_delivery_attempt()
        if hasta == "entregado":
            trabajo.record_attempt(DeliveryAttempt.create(
                delivery_job_id=trabajo.id, successful=True,
                evidence=DeliveryEvidence(recipient_name="Juan", pin_verified=True)))
        else:
            trabajo.record_attempt(DeliveryAttempt.create(
                delivery_job_id=trabajo.id, successful=False, failure_reason=motivo))
    DeliveryJobRepository(conn).save(trabajo)
    return trabajo


def _reentregar(conn, trabajo, *, hasta="pendiente", motivo="CUSTOMER_NOT_HOME"):
    """Como `ApproveRedeliveryUseCase`: el trabajo fallido queda en
    REDELIVERY_PENDING y la reentrega es un trabajo NUEVO del mismo pedido."""
    trabajo.request_redelivery()
    DeliveryJobRepository(conn).save(trabajo)
    return _trabajo(conn, "", branch_id=trabajo.branch_id, hasta=hasta, motivo=motivo,
                    order_id=trabajo.order_id)


def _sembrar_reentregas(conn, branch_id):
    """Como `RequestRedeliveryUseCase` y `ApproveRedeliveryUseCase`: la solicitud
    sale de un trabajo FALLIDO, y aprobarla crea un trabajo NUEVO."""
    trabajos = DeliveryJobRepository(conn)
    solicitudes = RedeliveryRequestRepository(conn)
    for etiqueta in ("pendiente", "aprobada", "rechazada"):
        trabajo = _trabajo(conn, etiqueta, branch_id=branch_id, hasta="fallido")
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


def _sembrar_seguimiento(conn, branch_id):
    _trabajo(conn, "asignado", branch_id=branch_id)
    _trabajo(conn, "en_camino", branch_id=branch_id, hasta="en_camino")
    _trabajo(conn, "entregado", branch_id=branch_id, hasta="entregado")
    _reentregar(conn, _trabajo(conn, "reentregado", branch_id=branch_id, hasta="fallido"))
    _pedido(conn, "mostrador", branch_id=branch_id)  # sin trabajo: no hay entrega que seguir


def _sembrar_incidencias(conn, branch_id):
    """Tres intentos fallidos, en este orden: dos del mismo pedido (el original y su
    reentrega) y uno de otro. Una entrega exitosa no es incidencia."""
    original = _trabajo(conn, "ausente", branch_id=branch_id, hasta="fallido",
                        motivo="CUSTOMER_NOT_HOME")
    _reentregar(conn, original, hasta="fallido", motivo="ADDRESS_NOT_FOUND")
    _trabajo(conn, "vehiculo", branch_id=branch_id, hasta="fallido", motivo="VEHICLE_FAILURE")
    _trabajo(conn, "entregado", branch_id=branch_id, hasta="entregado")


class _Sesion:
    """Sesión con todos los permisos del área: la auditoría la escriben los casos
    de uso, y éstos revalidan el permiso contra la sesión."""

    is_active = True
    user_id = USUARIO
    active_branch_id = SUCURSAL

    def tiene_permiso(self, code):
        return code in ALL_ORDERS_DELIVERY_PERMISSIONS


def _sembrar_auditoria(conn, branch_id):
    """Tres operaciones reales, tres acciones distintas."""
    politica = OrdersDeliveryAuthorizationPolicy(OrdersDeliverySessionPermissionChecker(_Sesion()))
    pedido = CreateCustomerOrderUseCase(politica).execute(
        conn, branch_id=branch_id, channel="POS", order_type="STANDARD",
        fulfillment_type="COUNTER", contact_name="auditado",
        lines=[{"product_id": new_uuid(), "unit_price": "80", "requested_quantity": "1"}],
        actor_user_id=USUARIO, operation_id=new_uuid())
    assert pedido.success, pedido.message
    confirmado = ConfirmCustomerOrderUseCase(politica).execute(
        conn, order_id=pedido.entity_id, actor_user_id=USUARIO, operation_id=new_uuid())
    assert confirmado.success, confirmado.message
    zona = CreateDeliveryZoneUseCase(politica).execute(
        conn, branch_id=branch_id, name="Centro", postal_codes="06000", minimum_order="0",
        delivery_fee="35", actor_user_id=USUARIO, operation_id=new_uuid())
    assert zona.success, zona.message


_SEMBRADORES = {
    DeliveryRecord.REDELIVERIES: _sembrar_reentregas,
    DeliveryRecord.CASH_COLLECTIONS: _sembrar_cobros,
    DeliveryRecord.SETTLEMENTS: _sembrar_liquidaciones,
    DeliveryRecord.ROUTES: _sembrar_rutas,
    DeliveryRecord.TRACKING: _sembrar_seguimiento,
    DeliveryRecord.INCIDENTS: _sembrar_incidencias,
    DeliveryRecord.AUDIT: _sembrar_auditoria,
}


def _sembrar(conn, record, branch_id=SUCURSAL):
    _SEMBRADORES[record](conn, branch_id)
    conn.commit()


def _pagina(conn, record, **kwargs):
    return DeliveryRecordsQueryService(conn).list_records(SUCURSAL, record, **kwargs)


def _estados(pagina, record):
    clave = _CLAVE_ESTADO.get(record, "status")
    return [fila[clave] for fila in pagina.rows]


#: Los registros de sucursal. Alertas es por persona y tiene sus propias pruebas.
_REGISTROS = sorted(set(DeliveryRecord) - PER_RECIPIENT_RECORDS, key=lambda r: r.value)


def test_every_record_is_covered_by_these_tests():
    assert set(_SEMBRADORES) | PER_RECIPIENT_RECORDS == set(DeliveryRecord)
    assert set(RUTA_A_REGISTRO.values()) == set(DeliveryRecord)


# -- lo que devuelve cada registro --------------------------------------------
@pytest.mark.parametrize("record", _REGISTROS, ids=lambda r: r.value)
def test_the_record_lists_everything_of_the_branch(conn, record):
    _sembrar(conn, record)

    pagina = _pagina(conn, record)

    assert sorted(_estados(pagina, record)) == sorted(SEMBRADOS[record])
    assert pagina.total == len(SEMBRADOS[record])


@pytest.mark.parametrize("record", _REGISTROS, ids=lambda r: r.value)
def test_what_needs_attention_comes_first(conn, record):
    _sembrar(conn, record)

    estados = _estados(_pagina(conn, record), record)
    primeros = len(SEMBRADOS[record]) - len(AL_FINAL[record])

    assert set(estados[primeros:]) == AL_FINAL[record], estados


@pytest.mark.parametrize("record", _REGISTROS, ids=lambda r: r.value)
def test_the_status_filter_returns_only_that_status(conn, record):
    _sembrar(conn, record)

    for estado in SEMBRADOS[record]:
        pagina = _pagina(conn, record, status=estado)
        assert _estados(pagina, record) == [estado]
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


@pytest.mark.parametrize("record", sorted(DeliveryRecord, key=lambda r: r.value),
                         ids=lambda r: r.value)
def test_every_status_has_a_label(record):
    assert set(STATUS_LABELS[record]) == {estado.value for estado in STATUS_ENUM[record]}


def test_the_audit_row_names_who_did_what_to_which_entity(conn):
    _sembrar(conn, DeliveryRecord.AUDIT)

    [zona] = _filas(conn, DeliveryRecord.AUDIT, status="DELIVERY_ZONE_CREATED")

    assert zona[1:4] == [USUARIO[:8], "Zona creada", "Zona"]
    assert zona[5] == "name: Centro; postal_codes: ['06000']; delivery_fee: 35"


def test_the_audit_only_shows_this_module(conn):
    """`audit_logs` es transversal: lo de Configuración no aparece aquí."""
    _sembrar(conn, DeliveryRecord.AUDIT)
    conn.execute("INSERT INTO audit_logs (id, accion, modulo, usuario, sucursal_id)"
                 " VALUES (?, 'ORDER_CREATED', 'CONFIGURACION', ?, ?)",
                 (new_uuid(), USUARIO, SUCURSAL))
    conn.commit()

    assert _pagina(conn, DeliveryRecord.AUDIT, status="ORDER_CREATED").total == 1


def test_every_payment_method_has_a_label():
    assert set(PAYMENT_METHOD_LABELS) == {m.value for m in CollectionPaymentMethod}


# -- seguimiento ------------------------------------------------------------------
def test_tracking_shows_the_latest_job_of_a_redelivered_order(conn):
    """El trabajo original quedó en REDELIVERY_PENDING; el pedido ya tiene otro."""
    _sembrar(conn, DeliveryRecord.TRACKING)

    reentregado = [f for f in _pagina(conn, DeliveryRecord.TRACKING).rows
                   if f["contact_name"] == "reentregado"]

    assert [f["job_status"] for f in reentregado] == ["PENDING_ASSIGNMENT"]
    assert _pagina(conn, DeliveryRecord.TRACKING, status="REDELIVERY_PENDING").total == 0


def test_an_order_without_delivery_is_not_tracked(conn):
    _sembrar(conn, DeliveryRecord.TRACKING)

    assert _pagina(conn, DeliveryRecord.TRACKING, query="mostrador").total == 0


def test_tracking_counts_the_attempts_of_the_current_job(conn):
    _sembrar(conn, DeliveryRecord.TRACKING)

    por_estado = {f[4]: f for f in _filas(conn, DeliveryRecord.TRACKING)}

    assert por_estado["Entregada"][9] == "1"
    assert por_estado["Entregada"][8] != "—"  # terminó: tiene fecha de entrega
    assert por_estado["Sin repartidor"][9] == "0"  # la reentrega aún no intenta nada
    assert por_estado["En camino"][6] != "—"  # despachado


# -- incidencias ------------------------------------------------------------------
def test_incidents_are_newest_first(conn):
    _sembrar(conn, DeliveryRecord.INCIDENTS)

    motivos = _estados(_pagina(conn, DeliveryRecord.INCIDENTS), DeliveryRecord.INCIDENTS)

    assert motivos == ["VEHICLE_FAILURE", "ADDRESS_NOT_FOUND", "CUSTOMER_NOT_HOME"]


def test_a_successful_attempt_is_not_an_incident(conn):
    _sembrar(conn, DeliveryRecord.INCIDENTS)

    assert _pagina(conn, DeliveryRecord.INCIDENTS, query="entregado").total == 0


def test_an_incident_shows_its_reason_and_where_the_delivery_is_now(conn):
    _sembrar(conn, DeliveryRecord.INCIDENTS)

    [vehiculo] = _filas(conn, DeliveryRecord.INCIDENTS, status="VEHICLE_FAILURE")
    [ausente] = _filas(conn, DeliveryRecord.INCIDENTS, status="CUSTOMER_NOT_HOME")

    assert vehiculo[3] == "vehiculo"
    assert vehiculo[5:] == ["Falla del vehículo", "—", "Fallida"]
    assert ausente[7] == "Reentrega pendiente"


# -- alertas: por persona -------------------------------------------------------------
def _usuario(conn, branch_id):
    """Un admin con el rol concedido en la sucursal, como lo resuelve el notificador."""
    user_id = new_uuid()
    rol = conn.execute("SELECT id FROM roles WHERE LOWER(nombre)='admin'").fetchone()[0]
    conn.execute(
        "INSERT INTO usuarios (id, nombre, usuario, password_hash, rol, sucursal_id, activo)"
        " VALUES (?,?,?,?,?,?,1)",
        (user_id, "Admin", f"admin-{user_id[-12:]}", "hash", "admin", branch_id))
    conn.execute("INSERT INTO usuarios_roles (usuario_id, rol_id, sucursal_id) VALUES (?,?,?)",
                 (user_id, rol, branch_id))
    return user_id


def _sembrar_alertas(conn):
    """Dos entregas fallidas en la sucursal, una en otra, y una notificación de otro
    módulo. El tipo va escrito aquí a propósito: es el que escribe
    `RecordDeliveryAttemptUseCase`, y la pantalla tiene que leer ESE."""
    yo, colega = _usuario(conn, SUCURSAL), _usuario(conn, SUCURSAL)
    _usuario(conn, OTRA_SUCURSAL)
    notificador = OrdersDeliveryInternalNotifier(conn)
    escritos = [
        notificador.notify_roles(roles=("admin",), branch_id=branch, tipo=tipo,
                                 titulo=titulo, cuerpo="CUSTOMER_NOT_HOME")
        for branch, tipo, titulo in (
            (SUCURSAL, "entrega_fallida", "Entrega fallida A"),
            (SUCURSAL, "entrega_fallida", "Entrega fallida B"),
            (OTRA_SUCURSAL, "entrega_fallida", "Entrega fallida C"),
            (SUCURSAL, "pedido_whatsapp_nuevo", "Pedido nuevo"),
        )
    ]
    # El notificador se traga sus errores y devuelve 0: sin esto la siembra podría
    # no escribir nada y las pruebas pasarían sobre una bandeja vacía.
    assert all(n >= 2 for n in escritos[:2]), escritos
    # Nadie en el backend marca alertas como leídas todavía; se simula al lector.
    conn.execute(
        "UPDATE notification_inbox SET leido=1, leido_at='2026-09-13T10:00:00+00:00'"
        " WHERE empleado_id=? AND titulo='Entrega fallida A'", (yo,))
    conn.commit()
    return yo, colega


def _alertas(conn, usuario, **kwargs):
    return DeliveryRecordsQueryService(conn).list_records(
        SUCURSAL, DeliveryRecord.ALERTS, recipient_user_id=usuario, **kwargs)


def test_alerts_are_my_own_delivery_alerts_unread_first(conn_completa):
    yo, _colega = _sembrar_alertas(conn_completa)

    pagina = _alertas(conn_completa, yo)

    assert [(f["title"], f["status"]) for f in pagina.rows] == [
        ("Entrega fallida B", "UNREAD"), ("Entrega fallida A", "READ")]
    assert pagina.total == 2


def test_what_a_colleague_read_is_still_unread_for_me(conn_completa):
    _yo, colega = _sembrar_alertas(conn_completa)

    assert {f["status"] for f in _alertas(conn_completa, colega).rows} == {"UNREAD"}


def test_the_alert_filter_splits_read_and_unread(conn_completa):
    yo, _colega = _sembrar_alertas(conn_completa)

    assert [f["title"] for f in _alertas(conn_completa, yo, status="UNREAD").rows] == [
        "Entrega fallida B"]
    assert [f["title"] for f in _alertas(conn_completa, yo, status="READ").rows] == [
        "Entrega fallida A"]


def test_alerts_without_a_user_are_rejected_not_shown_as_empty(conn_completa):
    _sembrar_alertas(conn_completa)

    with pytest.raises(ValueError):
        DeliveryRecordsQueryService(conn_completa).list_records(SUCURSAL, DeliveryRecord.ALERTS)


# -- las pantallas ------------------------------------------------------------
def test_the_route_registry_matches_the_specification():
    from frontend.desktop.modules.orders_delivery import orders_delivery_routes as rutas

    con_registro = {ruta for ruta, builder in rutas._REAL_ROUTE_BUILDERS.items()
                    if builder == "_build_delivery_record"}
    assert con_registro == set(rutas._DELIVERY_RECORD_BY_ROUTE) == set(RUTA_A_REGISTRO)
    for ruta, (nombre, _vacio) in rutas._DELIVERY_RECORD_BY_ROUTE.items():
        assert DeliveryRecord[nombre] is RUTA_A_REGISTRO[ruta], ruta


@pytest.mark.parametrize("ruta", sorted(r for r, rec in RUTA_A_REGISTRO.items()
                                        if rec not in PER_RECIPIENT_RECORDS))
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


def test_the_alerts_page_shows_the_session_users_alerts(app, conn_completa):
    from frontend.desktop.modules.orders_delivery.orders_delivery_routes import build_page

    yo, _colega = _sembrar_alertas(conn_completa)
    pagina = build_page("orders_alerts", conn_completa, branch_id=SUCURSAL, actor_user_id=yo)
    pagina.ensure_loaded()

    assert pagina._notice.isHidden(), pagina._notice.text()
    assert [pagina.table.item(fila, 1).text() for fila in range(pagina.table.rowCount())] == [
        "Entrega fallida B", "Entrega fallida A"]


def test_the_alerts_page_without_a_session_user_says_so(app, conn_completa):
    """Sin usuario no hay bandeja: la página lo dice en vez de pintar "no tienes
    alertas", que sería mentira."""
    from frontend.desktop.modules.orders_delivery.orders_delivery_routes import build_page

    _sembrar_alertas(conn_completa)
    pagina = build_page("orders_alerts", conn_completa, branch_id=SUCURSAL, actor_user_id=None)
    pagina.ensure_loaded()

    assert not pagina._notice.isHidden()
    assert "usuario" in pagina._notice.text()


def test_an_empty_record_shows_its_empty_state(app, conn):
    from frontend.desktop.modules.orders_delivery.orders_delivery_routes import build_page

    pagina = build_page("orders_settlements", conn, branch_id=SUCURSAL, actor_user_id=USUARIO)
    pagina.ensure_loaded()

    assert pagina._notice.isHidden(), pagina._notice.text()
    assert pagina.table.rowCount() == 0
    assert pagina._stack.currentWidget() is pagina._empty
