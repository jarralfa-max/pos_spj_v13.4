"""Resumen de Procesamiento Cárnico: los indicadores de la sucursal.

LO QUE SE FIJA
--------------
- Los cinco contadores "por atender" son LOS MISMOS del sidebar: el Resumen no
  los recalcula, así que la pantalla y el badge no pueden divergir.
- Órdenes por estado: sólo las de la sucursal y en el orden del ciclo de vida;
  el vocabulario lo garantiza el `CHECK` del esquema, no una revalidación.
- Producción del periodo: pesos sumados con `Decimal` (el esquema los guarda
  como TEXTO), sólo las salidas dentro de la ventana y de la sucursal.
"""
from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from backend.application.meat_processing.queries.meat_processing_badge_query_service import (
    MeatProcessingBadgeQueryService,
)
from backend.application.meat_processing.queries.meat_processing_overview_query_service import (
    MeatProcessingOverviewQueryService,
)
from backend.domain.meat_processing.enums import OutputType, ProcessingOrderStatus
from backend.infrastructure.db.schema import meat_processing_schema as esquema
from backend.infrastructure.db.schema.products_schema import create_products_schema
from backend.shared.ids import new_uuid
from frontend.desktop.modules.meat_processing.pages.meat_processing_overview_page import (
    MeatProcessingOverviewPage,
)
from frontend.desktop.modules.meat_processing.presenters.meat_processing_overview_presenter import (
    ATTENTION_KPIS,
    OUTPUT_TYPE_LABELS,
    MeatProcessingOverviewPresenter,
)
from frontend.desktop.modules.meat_processing.presenters.processing_order_presenter import (
    ORDER_STATUS_LABELS,
)
from tests.integration.meat_processing.test_meat_processing_records import (
    OTRA_SUCURSAL,
    SUCURSAL,
    USUARIO,
    Siembra,
)

AHORA = datetime(2026, 9, 23, 12, 0, tzinfo=timezone.utc)


@pytest.fixture
def conn():
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    create_products_schema(c)
    for crear in (esquema.create_meat_processing_schema,
                  esquema.create_meat_processing_preparation_execution_schema,
                  esquema.create_meat_processing_packaging_schema,
                  esquema.create_meat_processing_rework_schema,
                  esquema.create_meat_processing_genealogy_schema,
                  esquema.create_meat_processing_resources_schema,
                  esquema.create_meat_processing_output_results_schema):
        crear(c)
    c.commit()
    yield c
    c.close()


@pytest.fixture(scope="module")
def app():
    qt = pytest.importorskip("PyQt5.QtWidgets")
    yield qt.QApplication.instance() or qt.QApplication([])


def _orden(conn, estado, *, branch_id=SUCURSAL):
    orden = Siembra(conn, branch_id).orden()
    conn.execute("UPDATE processing_orders SET status=? WHERE id=?", (estado, orden.id))
    conn.commit()
    return orden


def _salida(conn, orden, *, tipo="MAIN_PRODUCT", peso="12.5", cantidad="4", cuando=None):
    conn.execute(
        "INSERT INTO process_outputs (id, operation_id, processing_order_id, product_id,"
        " warehouse_id, captured_by_user_id, output_type, quantity, weight, unit, produced_at)"
        " VALUES (?,?,?,?,?,?,?,?,?,'kg',?)",
        (new_uuid(), new_uuid(), orden.id, new_uuid(), new_uuid(), USUARIO, tipo,
         cantidad, peso, (cuando or AHORA).isoformat()))
    conn.commit()


def _servicio(conn):
    return MeatProcessingOverviewQueryService(conn)


# -- los contadores son los del sidebar ------------------------------------------
def test_the_attention_counters_are_the_sidebar_ones(conn):
    _orden(conn, ProcessingOrderStatus.PENDING_APPROVAL.value)
    _orden(conn, ProcessingOrderStatus.MATERIALS_PENDING.value)
    _orden(conn, ProcessingOrderStatus.CLOSED.value)

    resumen = _servicio(conn).overview(SUCURSAL, now=AHORA)

    assert resumen.attention == MeatProcessingBadgeQueryService(conn).get_badge_counts(SUCURSAL)
    assert resumen.attention["orders_needing_attention"] == 2


def test_every_attention_counter_has_a_card(conn):
    """Un contador nuevo en el sidebar sin tarjeta pasaría inadvertido."""
    claves = {clave for clave, _t, _i, _a in ATTENTION_KPIS}

    assert claves == set(_servicio(conn).overview(SUCURSAL, now=AHORA).attention)


# -- órdenes por estado ------------------------------------------------------------
def test_orders_are_counted_by_status_in_lifecycle_order(conn):
    _orden(conn, ProcessingOrderStatus.CLOSED.value)
    _orden(conn, ProcessingOrderStatus.DRAFT.value)
    _orden(conn, ProcessingOrderStatus.DRAFT.value)

    resumen = _servicio(conn).overview(SUCURSAL, now=AHORA)

    assert [(f.status, f.count) for f in resumen.by_status] == [("DRAFT", 2), ("CLOSED", 1)]


def test_orders_of_another_branch_are_not_counted(conn):
    _orden(conn, ProcessingOrderStatus.DRAFT.value, branch_id=OTRA_SUCURSAL)

    assert _servicio(conn).overview(SUCURSAL, now=AHORA).by_status == ()


# -- producción del periodo --------------------------------------------------------
def test_production_is_totalled_by_output_type(conn):
    orden = _orden(conn, ProcessingOrderStatus.CLOSED.value)
    _salida(conn, orden, peso="12.5", cantidad="4")
    _salida(conn, orden, peso="0.25", cantidad="1")
    _salida(conn, orden, tipo="WASTE", peso="1", cantidad="0")

    produccion = _servicio(conn).overview(SUCURSAL, now=AHORA).production

    assert [(f.output_type, f.outputs, f.weight, f.quantity) for f in produccion] == [
        ("MAIN_PRODUCT", 2, "12.75", "5"), ("WASTE", 1, "1", "0")]


def test_decimal_weights_are_not_rounded_through_a_float(conn):
    """El esquema guarda los decimales como TEXTO justamente por esto."""
    orden = _orden(conn, ProcessingOrderStatus.CLOSED.value)
    for _ in range(3):
        _salida(conn, orden, peso="0.1", cantidad="0")

    assert _servicio(conn).overview(SUCURSAL, now=AHORA).production[0].weight == "0.3"


def test_output_outside_the_window_is_not_counted(conn):
    orden = _orden(conn, ProcessingOrderStatus.CLOSED.value)
    _salida(conn, orden, cuando=AHORA - timedelta(days=9))

    assert _servicio(conn).overview(SUCURSAL, days=7, now=AHORA).production == ()
    assert _servicio(conn).overview(SUCURSAL, days=30, now=AHORA).production != ()


def test_output_of_another_branch_is_not_counted(conn):
    ajena = _orden(conn, ProcessingOrderStatus.CLOSED.value, branch_id=OTRA_SUCURSAL)
    _salida(conn, ajena)

    assert _servicio(conn).overview(SUCURSAL, now=AHORA).production == ()


def test_a_period_without_days_is_refused(conn):
    with pytest.raises(ValueError):
        _servicio(conn).overview(SUCURSAL, days=0, now=AHORA)


def test_the_schema_is_what_guarantees_the_vocabulary(conn):
    """El Resumen ordena por el enum y no revalida: si la base dejara de
    restringir el estado, esa confianza dejaría de estar justificada."""
    orden = _orden(conn, ProcessingOrderStatus.DRAFT.value)

    with pytest.raises(sqlite3.IntegrityError):
        conn.execute("UPDATE processing_orders SET status='INVENTADO' WHERE id=?", (orden.id,))
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            "INSERT INTO process_outputs (id, operation_id, processing_order_id, product_id,"
            " warehouse_id, captured_by_user_id, output_type, quantity, weight, unit,"
            " produced_at) VALUES (?,?,?,?,?,?,'INVENTADO','1','1','kg',?)",
            (new_uuid(), new_uuid(), orden.id, new_uuid(), new_uuid(), USUARIO,
             AHORA.isoformat()))


def test_every_output_type_has_a_label():
    assert {t.value for t in OutputType} <= set(OUTPUT_TYPE_LABELS)


def test_every_order_status_has_a_label():
    assert {s.value for s in ProcessingOrderStatus} <= set(ORDER_STATUS_LABELS)


# -- la pantalla -------------------------------------------------------------------
def _pagina(conn):
    return MeatProcessingOverviewPage(
        MeatProcessingOverviewPresenter(conn, branch_id=SUCURSAL),
        title="Resumen", subtitle="")


def test_the_route_opens_the_overview_page(app, conn):
    from backend.infrastructure.desktop.meat_processing_factory import (
        create_meat_processing_view,
    )

    class _Sesion:
        is_active = True
        user_id = USUARIO
        active_branch_id = SUCURSAL
        sucursal_id = SUCURSAL
        active_warehouse_id = new_uuid()
        permisos = frozenset()

        def tiene_permiso(self, code):
            return False

    pagina = create_meat_processing_view(conn, _Sesion())._page_builder("mp_overview")

    assert isinstance(pagina, MeatProcessingOverviewPage)


def test_the_page_shows_the_counters_and_the_tables(app, conn):
    _orden(conn, ProcessingOrderStatus.PENDING_APPROVAL.value)
    orden = _orden(conn, ProcessingOrderStatus.CLOSED.value)
    _salida(conn, orden, peso="12.5")
    pagina = _pagina(conn)

    pagina.ensure_loaded()

    tarjetas = {c.key: c.value for c in pagina.kpis._cards}
    assert tarjetas["orders_needing_attention"] == "1"
    assert pagina.status_table.item(0, 0).text() == ORDER_STATUS_LABELS["PENDING_APPROVAL"]
    assert pagina.production_table.item(0, 3).text() == "12.5 kg"
    assert pagina.production_table.item(0, 0).text() == OUTPUT_TYPE_LABELS["MAIN_PRODUCT"]


def test_a_counter_that_needs_attention_is_marked(app, conn):
    _orden(conn, ProcessingOrderStatus.PENDING_APPROVAL.value)
    pagina = _pagina(conn)

    pagina.ensure_loaded()

    variantes = {c.key: c.variant for c in pagina.kpis._cards}
    assert variantes["orders_needing_attention"] == "danger"
    assert variantes["active_orders"] == "primary"


def test_a_branch_without_orders_says_so(app, conn):
    pagina = _pagina(conn)

    pagina.ensure_loaded()

    assert "todavía no tiene órdenes" in pagina.period.text()
    assert pagina.status_table.rowCount() == 0


def test_the_share_of_each_status_is_shown(app, conn):
    for _ in range(3):
        _orden(conn, ProcessingOrderStatus.DRAFT.value)
    _orden(conn, ProcessingOrderStatus.CLOSED.value)
    pagina = _pagina(conn)

    pagina.ensure_loaded()

    assert pagina.status_table.item(0, 2).text() == "75%"


def test_the_page_loads_once(app, conn):
    """`ensure_loaded` se llama en cada visita a la ruta; `refresh` es lo que
    vuelve a consultar."""
    llamadas = []

    class _Presenter:
        def overview(self, *, days=7):
            llamadas.append(days)
            from frontend.desktop.modules.meat_processing.presenters.meat_processing_overview_presenter import (  # noqa: E501
                OverviewViewModel,
            )
            return OverviewViewModel()

    pagina = MeatProcessingOverviewPage(_Presenter(), title="Resumen", subtitle="")
    pagina.ensure_loaded()
    pagina.ensure_loaded()

    assert llamadas == [7]
    pagina.refresh()
    assert llamadas == [7, 7]
