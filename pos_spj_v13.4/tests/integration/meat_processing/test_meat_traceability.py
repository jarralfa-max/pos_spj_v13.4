"""Trazabilidad de Procesamiento Cárnico: de qué salió un lote y a dónde fue.

LO QUE SE FIJA
--------------
- Sólo se trazan lotes PRODUCIDOS por órdenes de la sucursal: un lote de otra
  sucursal no se traza, en vez de enseñar su producción.
- Las entradas salen de los CONSUMOS aplicados de la orden: todos los lotes de
  todos los insumos (una formulación o un consumo repartido tiene varios padres).
- La pantalla muestra el CÓDIGO del lote, nunca su identidad (UUIDv7).
- La genealogía NO se reimplementa aquí: el recorrido aguas arriba/abajo lo
  responde `TraceabilityQueryService` de INVENTARIO, que es quien guarda los
  enlaces que el adaptador de recepción de producción registra. La prueba lo
  comprueba con el servicio real y un enlace real, no con un doble.
"""
from __future__ import annotations

import sqlite3
from decimal import Decimal

import pytest

from backend.application.meat_processing.queries.lot_traceability_query_service import (
    ChainedConsumption,
    LotDestination,
    MeatLotTrace,
    MeatLotTraceabilityQueryService,
    ProducedLot,
)
from backend.domain.meat_processing.entities.material_consumption import MaterialConsumption
from backend.domain.meat_processing.entities.process_genealogy_link import ProcessGenealogyLink
from backend.domain.inventory.entities.traceability_link import TraceabilityLink
from backend.domain.inventory.enums import MovementType, TraceabilityLinkType
from backend.infrastructure.db.repositories.inventory.traceability_repository import (
    TraceabilityRepository,
)
from backend.infrastructure.db.repositories.meat_processing.output_results_repository import (
    ProcessingOutputResultsRepository,
)
from backend.infrastructure.db.schema import meat_processing_schema as esquema
from backend.infrastructure.db.schema.inventory_schema import create_inventory_schema
from backend.infrastructure.db.schema.products_schema import create_products_schema
from backend.shared.ids import is_uuidv7, new_uuid
from frontend.desktop.modules.meat_processing.pages.meat_traceability_page import (
    MeatTraceabilityPage,
)
from frontend.desktop.modules.meat_processing.presenters.meat_traceability_presenter import (
    MOVEMENT_LABELS,
    MeatTraceabilityPresenter,
)
from tests.integration.meat_processing.test_meat_processing_records import (
    OTRA_SUCURSAL,
    SUCURSAL,
    USUARIO,
    Siembra,
)


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
    # La genealogía de lotes es de Inventario: sus tablas son parte del recorrido.
    create_inventory_schema(c)
    c.commit()
    yield c
    c.close()


@pytest.fixture(scope="module")
def app():
    qt = pytest.importorskip("PyQt5.QtWidgets")
    yield qt.QApplication.instance() or qt.QApplication([])


def _lote(conn, valor: str) -> str:
    """Un lote real de Inventario: identidad UUIDv7 y el código que ve quien
    opera. Acepta el código (crea el lote la primera vez) o una identidad."""
    if is_uuidv7(valor):
        existe = conn.execute("SELECT 1 FROM inventory_lots WHERE id=?", (valor,)).fetchone()
        if existe is None:
            conn.execute("INSERT INTO inventory_lots (id, product_id, lot_code, origin_type,"
                         " created_at) VALUES (?,?,?,'PRODUCTION','2026-09-23')",
                         (valor, new_uuid(), f"COD-{valor[-6:]}"))
        return valor
    fila = conn.execute("SELECT id FROM inventory_lots WHERE lot_code=?", (valor,)).fetchone()
    if fila is not None:
        return fila[0]
    lot_id = new_uuid()
    conn.execute("INSERT INTO inventory_lots (id, product_id, lot_code, origin_type, created_at)"
                 " VALUES (?,?,?,'PRODUCTION','2026-09-23')", (lot_id, new_uuid(), valor))
    return lot_id


def _ejecutada(conn, *, branch_id=SUCURSAL, lote="LOTE-A1", producto="Pulpa",
               insumo="Canal de res", lote_entrada="LOTE-IN1", peso="60"):
    """Una orden con su consumo aplicado y su resultado por corte, como lo deja
    la ejecución."""
    siembra = Siembra(conn, branch_id)
    orden = siembra.orden()
    entrada = siembra.producto(insumo)
    lote, lote_entrada = _lote(conn, lote), _lote(conn, lote_entrada)
    consumo = MaterialConsumption(
        id=new_uuid(), operation_id=new_uuid(), processing_order_id=orden.id,
        product_id=entrada, warehouse_id=new_uuid(), captured_by_user_id=new_uuid(),
        planned_weight=Decimal("100"), unit="kg", lot_id=lote_entrada)
    consumo.record_actuals(actual_quantity=Decimal("0"), actual_weight=Decimal("100"))
    consumo.post(inventory_operation_id=new_uuid())
    siembra.guardar("consumptions", consumo)
    ProcessingOutputResultsRepository(conn).replace_for_order(orden.id, [{
        "product_id": siembra.producto(producto), "output_type": "MAIN_PRODUCT",
        "input_product_id": entrada, "input_weight": "100",
        "expected_weight": "65", "actual_weight": peso,
        "difference_weight": "-5", "expected_yield_pct": "65", "yield_pct": "60",
        "variance_pct": "-7.7",
        "input_lot_id": lote_entrada, "output_lot_id": lote,
    }])
    conn.commit()
    return orden


def _servicio(conn):
    return MeatLotTraceabilityQueryService(conn)


# -- qué lotes se pueden trazar ---------------------------------------------------
def test_the_search_lists_only_lots_this_branch_produced(conn):
    _ejecutada(conn, lote="LOTE-A1")
    _ejecutada(conn, lote="LOTE-A2", producto="Bistec")
    _ejecutada(conn, branch_id=OTRA_SUCURSAL, lote="LOTE-AJENO")

    lotes = _servicio(conn).search_lots(SUCURSAL)

    assert [lote.lot_code for lote in lotes] == ["LOTE-A2", "LOTE-A1"]


def test_the_search_filters_by_lot_or_product(conn):
    _ejecutada(conn, lote="LOTE-A1", producto="Pulpa")
    _ejecutada(conn, lote="LOTE-B2", producto="Bistec")

    servicio = _servicio(conn)

    assert [x.lot_code for x in servicio.search_lots(SUCURSAL, query="B2")] == ["LOTE-B2"]
    assert [x.lot_code for x in servicio.search_lots(SUCURSAL, query="Pulpa")] == ["LOTE-A1"]


def test_a_lot_of_another_branch_is_not_traced(conn):
    _ejecutada(conn, branch_id=OTRA_SUCURSAL, lote="LOTE-AJENO")

    assert _servicio(conn).trace(SUCURSAL, _lote(conn, "LOTE-AJENO")) is None


def test_an_unknown_lot_is_not_traced(conn):
    assert _servicio(conn).trace(SUCURSAL, "LOTE-QUE-NO-EXISTE") is None


# -- de qué salió ------------------------------------------------------------------
def test_the_trace_shows_the_order_and_the_input_lots_it_consumed(conn):
    orden = _ejecutada(conn, lote="LOTE-A1", insumo="Canal de res", lote_entrada="LOTE-IN1")

    recorrido = _servicio(conn).trace(SUCURSAL, _lote(conn, "LOTE-A1"))

    assert recorrido.produced.processing_order_id == orden.id
    assert recorrido.produced.product_name == "Pulpa"
    assert recorrido.produced.lot_code == "LOTE-A1"
    assert [(e.lot_id, e.lot_code, e.product_name) for e in recorrido.inputs] == [
        (_lote(conn, "LOTE-IN1"), "LOTE-IN1", "Canal de res")]


# -- a dónde fue: lo responde Inventario -------------------------------------------
def test_the_genealogy_comes_from_the_inventory_traceability_service(conn):
    """El enlace lo escribe Inventario (aquí, su repositorio real) y Cárnico lo lee
    por su servicio real: si dejara de consultarlo, esto se cae."""
    _ejecutada(conn, lote="LOTE-A1", lote_entrada="LOTE-IN1")
    TraceabilityRepository(conn).save(TraceabilityLink.create(
        parent_lot_id=_lote(conn, "LOTE-IN1"), child_lot_id=_lote(conn, "LOTE-A1"),
        link_type=TraceabilityLinkType.PRODUCTION, weight=60,
        source_module="meat_processing", created_by_user_id=USUARIO,
        operation_id=new_uuid()))
    conn.commit()

    recorrido = _servicio(conn).trace(SUCURSAL, _lote(conn, "LOTE-A1"))

    assert recorrido.parent_lot_ids == (_lote(conn, "LOTE-IN1"),)
    assert _lote(conn, "LOTE-A1") in recorrido.affected_lots
    assert recorrido.reaches_customers is False


def _encadenado(conn, lot_id, *, branch_id=SUCURSAL, insumo="Pulpa"):
    """El lote entra como consumo de OTRA orden: la arista entre órdenes que
    escribe `ChainOutputAsConsumptionUseCase` (PROC-18)."""
    siembra = Siembra(conn, branch_id)
    destino = siembra.orden()
    consumo = MaterialConsumption(
        id=new_uuid(), operation_id=new_uuid(), processing_order_id=destino.id,
        product_id=siembra.producto(insumo), warehouse_id=new_uuid(),
        captured_by_user_id=USUARIO, actual_weight=Decimal("8"), unit="kg")
    siembra.guardar("consumptions", consumo)
    siembra.guardar("genealogy_links", ProcessGenealogyLink(
        id=new_uuid(), operation_id=new_uuid(), upstream_entity_type="ProcessOutput",
        upstream_entity_id=new_uuid(), downstream_entity_type="MaterialConsumption",
        downstream_entity_id=consumo.id, product_id=consumo.product_id,
        lot_id=lot_id, weight=Decimal("8"), linked_by_user_id=USUARIO))
    conn.commit()
    return destino


def test_the_trace_shows_the_order_that_consumed_the_lot(conn):
    """PROC-18 construyó el grafo entre órdenes y nadie lo leía en producción."""
    lote = new_uuid()
    _ejecutada(conn, lote=lote)
    destino = _encadenado(conn, lote, insumo="Pulpa")

    recorrido = _servicio(conn).trace(SUCURSAL, lote)

    assert [(c.processing_order_id, c.product_name, c.weight) for c in recorrido.chained] == [
        (destino.id, "Pulpa", "8")]


def test_a_lot_nobody_chained_has_no_consuming_orders(conn):
    _ejecutada(conn, lote="LOTE-A1")

    assert _servicio(conn).trace(SUCURSAL, _lote(conn, "LOTE-A1")).chained == ()


def test_a_link_to_another_kind_of_entity_is_not_invented(conn):
    """El grafo es polimórfico a propósito; lo que no es un consumo no se
    traduce a una orden inexistente."""
    lote = new_uuid()
    _ejecutada(conn, lote=lote)
    Siembra(conn, SUCURSAL).guardar("genealogy_links", ProcessGenealogyLink(
        id=new_uuid(), operation_id=new_uuid(), upstream_entity_type="ProcessOutput",
        upstream_entity_id=new_uuid(), downstream_entity_type="InventoryLot",
        downstream_entity_id=new_uuid(), product_id=new_uuid(), lot_id=lote,
        weight=Decimal("8"), linked_by_user_id=USUARIO))
    conn.commit()

    assert _servicio(conn).trace(SUCURSAL, lote).chained == ()


def test_the_same_consumption_reached_twice_is_listed_once(conn):
    """El recorrido es un grafo: dos aristas pueden llegar al mismo consumo."""
    lote = new_uuid()
    _ejecutada(conn, lote=lote)
    destino = _encadenado(conn, lote)
    consumo = conn.execute(
        "SELECT id, product_id FROM material_consumptions WHERE processing_order_id=?",
        (destino.id,)).fetchone()
    Siembra(conn, SUCURSAL).guardar("genealogy_links", ProcessGenealogyLink(
        id=new_uuid(), operation_id=new_uuid(), upstream_entity_type="ProcessOutput",
        upstream_entity_id=new_uuid(), downstream_entity_type="MaterialConsumption",
        downstream_entity_id=consumo[0], product_id=consumo[1], lot_id=lote,
        weight=Decimal("3"), linked_by_user_id=USUARIO))
    conn.commit()

    recorrido = _servicio(conn).trace(SUCURSAL, lote)

    assert [c.processing_order_id for c in recorrido.chained] == [destino.id]


# -- la pantalla -------------------------------------------------------------------
LOTE_FALSO = new_uuid()


def _textos(tabla):
    return [tabla.item(r, c).text() for r in range(tabla.rowCount())
            for c in range(tabla.columnCount()) if tabla.item(r, c) is not None]


class _TrazaFalsa:
    """Un recorrido ya resuelto: la pantalla sólo tiene que pintarlo."""

    def __init__(self, conn):
        self._conn = conn

    def search_lots(self, branch_id, *, query="", limit=50):
        return [ProducedLot(lot_id=LOTE_FALSO, product_name="Pulpa",
                            output_type="MAIN_PRODUCT", weight="60",
                            produced_at="2026-09-23T10:00:00+00:00",
                            processing_order_id=new_uuid(), process_type="CUTTING",
                            lot_code="LOTE-A1")]

    def trace(self, branch_id, lot_id):
        return MeatLotTrace(
            produced=self.search_lots(branch_id)[0],
            destinations=(LotDestination(
                occurred_at="2026-09-23T12:00:00+00:00",
                movement_type=MovementType.SALE_ISSUE.value, source_module="sales",
                source_document_type="SALE", source_document_id=new_uuid(),
                branch_id=SUCURSAL, quantity="1", weight="12", branch_name="Centro"),),
            chained=(ChainedConsumption(
                processing_order_id=new_uuid(), process_type="GRINDING",
                product_name="Pulpa", quantity="4", weight="8",
                linked_at="2026-09-23T13:00:00+00:00",
                order_created_at="2026-09-23T11:00:00+00:00"),),
            affected_lots=(LOTE_FALSO,), reaches_customers=True,
            branches_touched=(SUCURSAL,))


def _presenter(conn, *, falso=False):
    return MeatTraceabilityPresenter(
        conn, branch_id=SUCURSAL,
        service_factory=_TrazaFalsa if falso else MeatLotTraceabilityQueryService)


def test_the_route_opens_the_traceability_page(app, conn):
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

    pagina = create_meat_processing_view(conn, _Sesion())._page_builder("mp_traceability")

    assert isinstance(pagina, MeatTraceabilityPage)


def test_the_page_shows_where_the_lot_came_from(app, conn):
    _ejecutada(conn, lote="LOTE-A1", lote_entrada="LOTE-IN1")
    pagina = MeatTraceabilityPage(_presenter(conn), title="Trazabilidad", subtitle="")
    pagina.ensure_loaded()

    pagina.show_lot(_lote(conn, "LOTE-A1"))

    assert pagina.inputs_table.rowCount() == 1
    assert pagina.inputs_table.item(0, 0).text() == "LOTE-IN1"
    assert "Pulpa" in pagina.summary.text()


def test_the_page_says_when_the_lot_is_not_from_this_branch(app, conn):
    _ejecutada(conn, branch_id=OTRA_SUCURSAL, lote="LOTE-AJENO")
    pagina = MeatTraceabilityPage(_presenter(conn), title="Trazabilidad", subtitle="")

    pagina.show_lot(_lote(conn, "LOTE-AJENO"))

    assert "no lo produjo esta sucursal" in pagina.summary.text()
    assert pagina.inputs_table.rowCount() == 0


def test_the_page_renders_the_downstream_movements(app, conn):
    pagina = MeatTraceabilityPage(_presenter(conn, falso=True), title="Trazabilidad", subtitle="")

    pagina.show_lot(LOTE_FALSO)

    assert [pagina.destinations_table.item(0, c).text() for c in (1, 2, 3, 4)] == [
        "Venta", "sales", "Venta", "Centro"]
    assert "Llegó a clientes" in pagina.origin.text()


def test_the_page_renders_the_order_that_consumed_the_lot(app, conn):
    pagina = MeatTraceabilityPage(_presenter(conn, falso=True), title="Trazabilidad", subtitle="")

    pagina.show_lot(LOTE_FALSO)

    assert [pagina.chained_table.item(0, c).text() for c in (0, 1, 2, 3)] == [
        "Orden del 2026-09-23 11:00", "Molido", "Pulpa", "8 kg"]


def test_the_page_never_shows_an_identity(app, conn):
    """Lotes, órdenes, documentos y sucursales se muestran por lo que el operador
    reconoce (código, fecha, tipo, nombre), nunca por su UUID."""
    pagina = MeatTraceabilityPage(_presenter(conn, falso=True), title="Trazabilidad", subtitle="")
    pagina.show_lot(LOTE_FALSO)
    textos = (_textos(pagina.inputs_table) + _textos(pagina.chained_table)
              + _textos(pagina.destinations_table) + [pagina.summary.text(),
                                                      pagina.origin.text()])
    assert textos and not any(is_uuidv7(t) for t in textos)
    assert not any(parte in t for t in textos for parte in (LOTE_FALSO[:8], SUCURSAL[:8]))


def test_every_movement_type_has_a_label():
    assert {m.value for m in MovementType} <= set(MOVEMENT_LABELS)
