"""Registros de Procesamiento Cárnico (PASS 6): lo que enseña cada pantalla.

LO QUE SE FIJA
--------------
- Cada registro devuelve todo lo suyo y sólo lo suyo. Salvo órdenes y auditoría,
  ninguna tabla tiene `branch_id`: la sucursal es la de la orden. Sin ese JOIN
  cada sucursal vería la producción de todas.
- Lo que pide atención va arriba; el filtro por estado devuelve sólo ese estado; un
  estado inventado se rechaza en vez de dar una lista vacía que parece real.
- Despiece y Productos derivados son las salidas de familias de proceso distintas.
- Los badges cuentan EXACTAMENTE lo "por atender" de su registro.

Todo se siembra con las entidades del dominio y la unidad de trabajo del módulo,
llevando cada una a su estado por sus propios métodos (`start`, `pause`, `approve`…).
"""
from __future__ import annotations

import sqlite3
from decimal import Decimal

import pytest

from backend.application.meat_processing.queries.meat_processing_badge_query_service import (
    BADGE_RECORDS,
    MeatProcessingBadgeQueryService,
)
from backend.application.meat_processing.queries.meat_processing_records_query_service import (
    ATTENTION,
    SEARCHABLE_RECORDS,
    STATUS_ENUM,
    MeatProcessingRecord,
    MeatProcessingRecordsQueryService,
)
from backend.domain.meat_processing.entities import (
    MaterialConsumption,
    MaterialRequirement,
    PackagingExecution,
    ProcessExecution,
    ProcessIncident,
    ProcessingBatch,
    ProcessingOrder,
    ProcessOutput,
    ProcessWeighing,
    ProductionLabel,
    ReworkOrder,
    YieldReconciliation,
)
from backend.domain.meat_processing.enums import (
    IncidentType,
    OutputQualityStatus,
    OutputType,
    ProcessType,
    ReworkOrigin,
    WeighingType,
    YieldStatus,
)
from backend.infrastructure.db.repositories.meat_processing.unit_of_work import (
    MeatProcessingUnitOfWork,
)
from backend.infrastructure.db.schema import meat_processing_schema as esquema
from backend.infrastructure.db.schema.products_schema import create_products_schema
from backend.shared.ids import new_uuid
from frontend.desktop.modules.meat_processing.presenters.meat_processing_record_presenter import (
    STATUS_LABELS,
    MeatProcessingRecordPresenter,
)

SUCURSAL = new_uuid()
OTRA_SUCURSAL = new_uuid()
USUARIO = new_uuid()

R = MeatProcessingRecord

SEMBRADOS = {
    R.PREPARATION: {"REQUIRED", "RESERVED", "CANCELLED"},
    R.ACTIVE_PROCESSING: {"NOT_STARTED", "ACTIVE", "PAUSED", "COMPLETED"},
    R.WEIGHINGS: {"INPUT", "OUTPUT", "WASTE"},
    R.CONSUMPTIONS: {"DRAFT", "POSTED", "REVERSED"},
    R.CUTTING: {"MAIN_PRODUCT", "CO_PRODUCT"},
    R.DERIVED_PRODUCTS: {"BY_PRODUCT"},
    R.PACKAGING: {"UNLABELED", "LABELED"},
    R.PRODUCED_LOTS: {"PLANNED", "IN_PROGRESS", "COMPLETED"},
    R.YIELDS: {"PENDING_REVIEW", "WITHIN_TOLERANCE", "CRITICAL"},
    R.QUALITY: {"PENDING_INSPECTION", "QUARANTINED", "RELEASED"},
    R.REWORK: {"CREATED", "APPROVED", "CANCELLED"},
    R.INCIDENTS: {"OPEN", "UNDER_REVIEW", "RESOLVED"},
    R.AUDIT: {"ProcessingOrder", "ProcessIncident", "ProductionAlert"},
}

#: Columna que hace de "estado" en cada registro.
_CLAVE = {R.WEIGHINGS: "weighing_type", R.CUTTING: "output_type",
          R.DERIVED_PRODUCTS: "output_type", R.QUALITY: "quality_status",
          R.AUDIT: "entity_type"}


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
                  esquema.create_meat_processing_resources_schema):
        crear(c)
    c.commit()
    yield c
    c.close()


# -- siembra por dominio ----------------------------------------------------
class Siembra:
    def __init__(self, conn, branch_id):
        self.conn = conn
        self.branch_id = branch_id
        self.uow = MeatProcessingUnitOfWork(conn)

    def guardar(self, repo, *entidades):
        with self.uow:
            for entidad in entidades:
                getattr(self.uow, repo).save(entidad)

    def producto(self, nombre):
        pid = new_uuid()
        self.conn.execute(
            "INSERT INTO products (id, code, name, name_normalized, product_type,"
            " lifecycle_status, base_unit_id) VALUES (?,?,?,?,'RESALE_PRODUCT','ACTIVE','kg')",
            (pid, f"C-{pid[-8:]}", nombre, nombre.lower()))
        self.conn.commit()
        return pid

    def orden(self, tipo=ProcessType.CUTTING, producto="Arrachera"):
        orden = ProcessingOrder(
            id=new_uuid(), operation_id=new_uuid(), branch_id=self.branch_id,
            warehouse_id=new_uuid(), process_type=tipo,
            target_product_id=self.producto(producto), created_by_user_id=USUARIO,
            planned_quantity=Decimal("10"), planned_weight=Decimal("100"))
        self.guardar("orders", orden)
        return orden

    def salida(self, orden, tipo=OutputType.MAIN_PRODUCT, producto="Pulpa"):
        return ProcessOutput(
            id=new_uuid(), operation_id=new_uuid(), processing_order_id=orden.id,
            product_id=self.producto(producto), warehouse_id=new_uuid(),
            captured_by_user_id=USUARIO, output_type=tipo, quantity=Decimal("4"),
            weight=Decimal("12.5"), unit="kg")


def _preparacion(s):
    orden = s.orden()
    requerido, reservado, cancelado = (
        MaterialRequirement(id=new_uuid(), operation_id=new_uuid(), processing_order_id=orden.id,
                            product_id=s.producto(nombre), required_weight=Decimal("10"), unit="kg")
        for nombre in ("Sal", "Pimienta", "Ajo"))
    reservado.reserve(weight=Decimal("10"))
    cancelado.cancel()
    s.guardar("material_requirements", requerido, reservado, cancelado)


def _ejecuciones(s):
    orden = s.orden()
    ejecuciones = [ProcessExecution(id=new_uuid(), operation_id=new_uuid(),
                                    processing_order_id=orden.id) for _ in range(4)]
    _, activa, pausada, completa = ejecuciones
    activa.start()
    pausada.start()
    pausada.pause()
    completa.start()
    completa.complete()
    s.guardar("executions", *ejecuciones)


def _pesajes(s):
    orden = s.orden()
    s.guardar("weighings", *(
        ProcessWeighing(id=new_uuid(), operation_id=new_uuid(), processing_order_id=orden.id,
                        captured_by_user_id=USUARIO, weighing_type=tipo,
                        gross_weight=Decimal("10"), tare_weight=Decimal("1"))
        for tipo in (WeighingType.INPUT, WeighingType.OUTPUT, WeighingType.WASTE)))


def _consumos(s):
    orden = s.orden()
    borrador, aplicado, revertido = (
        MaterialConsumption(id=new_uuid(), operation_id=new_uuid(), processing_order_id=orden.id,
                            product_id=s.producto(nombre), warehouse_id=new_uuid(),
                            captured_by_user_id=USUARIO, planned_weight=Decimal("10"), unit="kg")
        for nombre in ("Res", "Cerdo", "Pollo"))
    for consumo in (aplicado, revertido):
        consumo.record_actuals(actual_quantity=Decimal("1"), actual_weight=Decimal("9"))
        consumo.post(inventory_operation_id=new_uuid())
    revertido.reverse()
    s.guardar("consumptions", borrador, aplicado, revertido)


def _salidas(s):
    """Dos salidas de corte (Despiece) y una de molido (Productos derivados)."""
    corte = s.orden(ProcessType.CUTTING)
    molido = s.orden(ProcessType.GRINDING)
    s.guardar("outputs", s.salida(corte, OutputType.MAIN_PRODUCT),
              s.salida(corte, OutputType.CO_PRODUCT), s.salida(molido, OutputType.BY_PRODUCT))


def _empaques(s):
    orden = s.orden()
    empaques = [PackagingExecution(
        id=new_uuid(), operation_id=new_uuid(), processing_order_id=orden.id,
        product_id=s.producto(nombre), packaging_material_id=new_uuid(), package_quantity=5,
        net_weight=Decimal("10"), gross_weight=Decimal("11"), packaged_by_user_id=USUARIO)
        for nombre in ("Molida 1kg", "Bistec 500g")]
    etiqueta = ProductionLabel(
        id=new_uuid(), operation_id=new_uuid(), packaging_execution_id=empaques[1].id,
        label_template_id=new_uuid(), barcode="7501", qr_traceability_reference="QR-1")
    etiqueta.mark_printed(actor_user_id=USUARIO)
    s.guardar("packaging_executions", *empaques)
    s.guardar("production_labels", etiqueta)


def _lotes(s):
    orden = s.orden()
    lotes = [ProcessingBatch(id=new_uuid(), operation_id=new_uuid(), processing_order_id=orden.id,
                             batch_number=f"LPR-{new_uuid()[-8:]}") for _ in range(3)]
    _, en_proceso, completo = lotes
    en_proceso.start()
    completo.start()
    completo.complete()
    s.guardar("batches", *lotes)


def _rendimientos(s):
    orden = s.orden()
    conciliaciones = [YieldReconciliation(
        id=new_uuid(), operation_id=new_uuid(), processing_order_id=orden.id,
        input_quantity=Decimal("10"), input_weight=Decimal("100"),
        expected_output_quantity=Decimal("8"), expected_output_weight=Decimal("80"),
        actual_output_quantity=Decimal("8"), actual_output_weight=Decimal("78"),
        tolerance_pct=Decimal("5")) for _ in range(3)]
    _, dentro, critico = conciliaciones
    dentro.apply_classification(YieldStatus.WITHIN_TOLERANCE)
    critico.apply_classification(YieldStatus.CRITICAL)
    s.guardar("yield_reconciliations", *conciliaciones)


def _calidad(s):
    orden = s.orden()
    pendiente, cuarentena, liberada = (s.salida(orden) for _ in range(3))
    cuarentena.mark_quality_status(OutputQualityStatus.QUARANTINED)
    liberada.mark_quality_status(OutputQualityStatus.RELEASED)
    s.guardar("outputs", pendiente, cuarentena, liberada)


def _reprocesos(s):
    orden = s.orden()
    origen = s.salida(orden)
    s.guardar("outputs", origen)
    creado, aprobado, cancelado = (
        ReworkOrder(id=new_uuid(), operation_id=new_uuid(), source_output_id=origen.id,
                    product_id=s.producto(nombre), origin=ReworkOrigin.QUALITY_DECISION,
                    created_by_user_id=USUARIO, weight=Decimal("5"), reason=f"hueso en {nombre}")
        for nombre in ("Pierna", "Lomo", "Costilla"))
    aprobado.approve(actor_user_id=new_uuid())
    cancelado.cancel()
    s.guardar("rework_orders", creado, aprobado, cancelado)


def _incidencias(s):
    orden = s.orden()
    abierta, revision, resuelta = (
        ProcessIncident(id=new_uuid(), operation_id=new_uuid(), processing_order_id=orden.id,
                        incident_type=IncidentType.EQUIPMENT_FAILURE, reported_by_user_id=USUARIO,
                        description=f"sierra {n} detenida") for n in (1, 2, 3))
    revision.start_review()
    resuelta.start_review()
    resuelta.resolve(actor_user_id=USUARIO, resolution_notes="cambio de banda")
    s.guardar("incidents", abierta, revision, resuelta)


def _auditoria(s):
    orden = s.orden()
    with s.uow:
        for tipo, accion in (("ProcessingOrder", "CREATED"), ("ProcessIncident", "REPORTED"),
                             ("ProductionAlert", "REQUESTED")):
            s.uow.audit.record(entity_type=tipo, entity_id=orden.id, action=accion,
                               user_id=USUARIO, branch_id=s.branch_id)


_SEMBRADORES = {
    R.PREPARATION: _preparacion, R.ACTIVE_PROCESSING: _ejecuciones, R.WEIGHINGS: _pesajes,
    R.CONSUMPTIONS: _consumos, R.CUTTING: _salidas, R.DERIVED_PRODUCTS: _salidas,
    R.PACKAGING: _empaques, R.PRODUCED_LOTS: _lotes, R.YIELDS: _rendimientos,
    R.QUALITY: _calidad, R.REWORK: _reprocesos, R.INCIDENTS: _incidencias, R.AUDIT: _auditoria,
}


def _sembrar(conn, record, branch_id=SUCURSAL):
    _SEMBRADORES[record](Siembra(conn, branch_id))


def _pagina(conn, record, **kwargs):
    return MeatProcessingRecordsQueryService(conn).list_records(SUCURSAL, record, **kwargs)


def _estados(pagina, record):
    return [fila[_CLAVE.get(record, "status")] for fila in pagina.rows]


_REGISTROS = sorted(MeatProcessingRecord, key=lambda r: r.value)


def test_every_record_is_seeded():
    assert set(_SEMBRADORES) == set(SEMBRADOS) == set(MeatProcessingRecord)


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
    atencion = {e.value for e in ATTENTION[record]}
    primeros = [e for e in estados if e in atencion]

    assert estados[:len(primeros)] == primeros, estados


@pytest.mark.parametrize("record", _REGISTROS, ids=lambda r: r.value)
def test_the_status_filter_returns_only_that_status(conn, record):
    _sembrar(conn, record)

    for estado in SEMBRADOS[record]:
        pagina = _pagina(conn, record, status=estado)
        assert _estados(pagina, record) == [estado]
        assert pagina.total == 1


@pytest.mark.parametrize("record", _REGISTROS, ids=lambda r: r.value)
def test_an_unknown_status_is_rejected(conn, record):
    with pytest.raises(ValueError):
        _pagina(conn, record, status="NO_EXISTE")


@pytest.mark.parametrize("record", _REGISTROS, ids=lambda r: r.value)
def test_another_branch_never_leaks_into_the_record(conn, record):
    _sembrar(conn, record)
    antes = _pagina(conn, record)

    _sembrar(conn, record, branch_id=OTRA_SUCURSAL)
    despues = _pagina(conn, record)

    assert (despues.rows, despues.total) == (antes.rows, antes.total)


@pytest.mark.parametrize("record", _REGISTROS, ids=lambda r: r.value)
def test_every_status_has_a_label(record):
    assert set(STATUS_LABELS[record]) == {e.value for e in STATUS_ENUM[record]}


def test_cutting_and_derived_products_split_by_process_family(conn):
    _sembrar(conn, R.CUTTING)

    corte = {f["process_type"] for f in _pagina(conn, R.CUTTING).rows}
    derivados = {f["process_type"] for f in _pagina(conn, R.DERIVED_PRODUCTS).rows}

    assert (corte, derivados) == ({"CUTTING"}, {"GRINDING"})


def test_search_finds_by_product_and_description(conn):
    _sembrar(conn, R.PREPARATION)
    _sembrar(conn, R.INCIDENTS)

    assert [f["product_name"] for f in _pagina(conn, R.PREPARATION, query="pimienta").rows] == [
        "Pimienta"]
    assert _pagina(conn, R.INCIDENTS, query="sierra 2").total == 1


def test_every_record_is_searchable():
    assert SEARCHABLE_RECORDS == set(MeatProcessingRecord)


# -- formato ------------------------------------------------------------------------
def _filas(conn, record, **kwargs):
    return MeatProcessingRecordPresenter(conn, branch_id=SUCURSAL, record=record).rows(**kwargs)


def test_a_yield_row_shows_its_variance_against_expected(conn):
    _sembrar(conn, R.YIELDS)

    modelo = _filas(conn, R.YIELDS, status="CRITICAL")

    assert modelo.total == 1
    assert modelo.rows[0][7:] == ["-2.5%", "5%", "Crítico"]


def test_a_weighing_row_shows_its_net_weight(conn):
    _sembrar(conn, R.WEIGHINGS)

    [fila] = _filas(conn, R.WEIGHINGS, status="INPUT").rows

    assert fila[3:7] == ["Entrada", "10", "1", "9"]


def test_a_packaging_row_shows_its_labels(conn):
    _sembrar(conn, R.PACKAGING)

    [fila] = _filas(conn, R.PACKAGING, status="LABELED").rows

    assert (fila[1], fila[6], fila[8]) == ("Bistec 500g", "1", "Etiquetado")


# -- badges --------------------------------------------------------------------------
@pytest.mark.parametrize("clave, record", sorted(BADGE_RECORDS.items()))
def test_the_badge_counts_what_needs_attention_in_its_list(conn, clave, record):
    _sembrar(conn, record)
    _sembrar(conn, record, branch_id=OTRA_SUCURSAL)

    badge = MeatProcessingBadgeQueryService(conn).get_badge_counts(SUCURSAL)[clave]
    en_lista = sum(_pagina(conn, record, status=e.value).total for e in ATTENTION[record])

    assert badge == en_lista > 0


def test_the_orders_badge_counts_orders_waiting_on_someone(conn):
    s = Siembra(conn, SUCURSAL)
    borrador = s.orden()
    por_aprobar = s.orden()
    por_aprobar.submit_for_approval()
    s.guardar("orders", borrador, por_aprobar)

    assert MeatProcessingBadgeQueryService(conn).get_badge_counts(SUCURSAL)[
        "orders_needing_attention"] == 1


# -- la tabla de rutas del factory ---------------------------------------------------
def test_the_factory_route_tuple_is_the_record_route_table():
    """El `page_builder` del factory compara contra una tupla LITERAL porque el
    trinquete de rutas reales lee el código, no lo ejecuta. Esa tupla y
    `_RECORD_ROUTES` no pueden divergir: una ruta en la tabla sin rama en el
    builder caería al placeholder sin que nada lo dijera."""
    import ast
    import inspect

    from backend.infrastructure.desktop import meat_processing_factory as factory

    arbol = ast.parse(inspect.getsource(factory.__dict__["_build_meat_processing_wiring"]))
    [tupla] = [comparador for nodo in ast.walk(arbol) if isinstance(nodo, ast.Compare)
               for comparador in nodo.comparators if isinstance(comparador, ast.Tuple)]

    assert {e.value for e in tupla.elts} == set(factory._RECORD_ROUTES)
    assert {nombre for nombre, _ in factory._RECORD_ROUTES.values()} <= {
        r.name for r in MeatProcessingRecord}


def test_a_label_that_was_never_printed_leaves_the_package_unlabeled(conn):
    """Una etiqueta generada pero no impresa no sirve en el anaquel: el empaque
    sigue "Sin etiqueta". Sin este caso, contar cualquier etiqueta pasaría igual."""
    _sembrar(conn, R.PACKAGING)
    s = Siembra(conn, SUCURSAL)
    orden = s.orden()
    empaque = PackagingExecution(
        id=new_uuid(), operation_id=new_uuid(), processing_order_id=orden.id,
        product_id=s.producto("Chuleta"), packaging_material_id=new_uuid(), package_quantity=2,
        net_weight=Decimal("4"), gross_weight=Decimal("4.2"), packaged_by_user_id=USUARIO)
    s.guardar("packaging_executions", empaque)
    s.guardar("production_labels", ProductionLabel(
        id=new_uuid(), operation_id=new_uuid(), packaging_execution_id=empaque.id,
        label_template_id=new_uuid(), barcode="7502", qr_traceability_reference="QR-2"))

    assert _pagina(conn, R.PACKAGING, status="UNLABELED").total == 2
    assert _pagina(conn, R.PACKAGING, status="LABELED").total == 1
