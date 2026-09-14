"""MeatProcessingRecordsQueryService — los registros de Procesamiento Cárnico.

Una consulta por pantalla del sidebar que tiene datos reales detrás: requerimientos
de material (Preparación), ejecuciones (En proceso), pesajes, consumos, salidas de
despiece y de derivados, empaques, lotes producidos, conciliaciones de rendimiento,
calidad de salidas, reprocesos, incidencias y auditoría.

DE QUÉ SUCURSAL ES CADA COSA
----------------------------
Sólo `processing_orders` y `meat_processing_audit_log` tienen `branch_id`. Todo lo
demás cuelga de una orden, y la sucursal se filtra por `processing_orders.branch_id`
con un JOIN; sin él cada sucursal vería la producción de todas. Un reproceso cuelga
de la salida que lo originó (o de su orden de reproceso, si ya tiene una).

LO QUE PIDE ATENCIÓN VA ARRIBA
------------------------------
Cada registro tiene sus estados "por atender" (un requerimiento sin reservar, una
ejecución pausada, un rendimiento fuera de tolerancia, una salida en cuarentena…).
`MeatProcessingBadgeQueryService` cuenta EXACTAMENTE esos estados, con esta misma
definición: el contador y la lista no pueden decir cosas distintas.

Las lecturas van directo a las tablas: los repositorios hidratan agregados uno por
orden y no paginan. Las escrituras siguen yendo por los casos de uso.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from backend.domain.meat_processing.enums import (
    ConsumptionStatus,
    ExecutionStatus,
    IncidentStatus,
    MaterialRequirementStatus,
    OutputQualityStatus,
    OutputType,
    ProcessingBatchStatus,
    ProcessType,
    ReworkOrderStatus,
    WeighingType,
    YieldStatus,
)


class MeatProcessingRecord(str, Enum):
    PREPARATION = "preparation"
    ACTIVE_PROCESSING = "active_processing"
    WEIGHINGS = "weighings"
    CONSUMPTIONS = "consumptions"
    CUTTING = "cutting"
    DERIVED_PRODUCTS = "derived_products"
    PACKAGING = "packaging"
    PRODUCED_LOTS = "produced_lots"
    YIELDS = "yields"
    QUALITY = "quality"
    REWORK = "rework"
    INCIDENTS = "incidents"
    AUDIT = "audit"


class PackagingLabelStatus(str, Enum):
    """Si el empaque ya tiene etiqueta impresa. No hay columna: se deriva."""

    UNLABELED = "UNLABELED"
    LABELED = "LABELED"


class AuditEntity(str, Enum):
    """Tipos de entidad que los casos de uso anotan en la auditoría del módulo."""

    PROCESSING_ORDER = "ProcessingOrder"
    MATERIAL_REQUIREMENT = "MaterialRequirement"
    MATERIAL_CONSUMPTION = "MaterialConsumption"
    PROCESS_OUTPUT = "ProcessOutput"
    YIELD_RECONCILIATION = "YieldReconciliation"
    PROCESS_INCIDENT = "ProcessIncident"
    REWORK_ORDER = "ReworkOrder"
    OPERATOR_ASSIGNMENT = "OperatorAssignment"
    EQUIPMENT_ASSIGNMENT = "EquipmentAssignment"
    PRODUCTION_EQUIPMENT = "ProductionEquipment"
    PRODUCTION_ALERT = "ProductionAlert"


#: Tipos de proceso de cada pantalla de salidas. Los `_FUTURE` no tienen flujo.
CUTTING_PROCESS_TYPES = (ProcessType.CUTTING, ProcessType.DISASSEMBLY, ProcessType.DEBONING,
                         ProcessType.TRIMMING, ProcessType.PORTIONING)
DERIVED_PROCESS_TYPES = (ProcessType.GRINDING, ProcessType.MIXING, ProcessType.MARINATION,
                         ProcessType.FORMULATION)

STATUS_ENUM: dict[MeatProcessingRecord, type[Enum]] = {
    MeatProcessingRecord.PREPARATION: MaterialRequirementStatus,
    MeatProcessingRecord.ACTIVE_PROCESSING: ExecutionStatus,
    MeatProcessingRecord.WEIGHINGS: WeighingType,
    MeatProcessingRecord.CONSUMPTIONS: ConsumptionStatus,
    MeatProcessingRecord.CUTTING: OutputType,
    MeatProcessingRecord.DERIVED_PRODUCTS: OutputType,
    MeatProcessingRecord.PACKAGING: PackagingLabelStatus,
    MeatProcessingRecord.PRODUCED_LOTS: ProcessingBatchStatus,
    MeatProcessingRecord.YIELDS: YieldStatus,
    MeatProcessingRecord.QUALITY: OutputQualityStatus,
    MeatProcessingRecord.REWORK: ReworkOrderStatus,
    MeatProcessingRecord.INCIDENTS: IncidentStatus,
    MeatProcessingRecord.AUDIT: AuditEntity,
}

#: Estados que piden que alguien haga algo. Van arriba y son los que cuentan los badges.
ATTENTION: dict[MeatProcessingRecord, tuple[Enum, ...]] = {
    MeatProcessingRecord.PREPARATION: (
        MaterialRequirementStatus.REQUIRED, MaterialRequirementStatus.RESERVED),
    MeatProcessingRecord.ACTIVE_PROCESSING: (ExecutionStatus.ACTIVE, ExecutionStatus.PAUSED),
    MeatProcessingRecord.WEIGHINGS: (),
    MeatProcessingRecord.CONSUMPTIONS: (
        ConsumptionStatus.DRAFT, ConsumptionStatus.PENDING_POSTING),
    MeatProcessingRecord.CUTTING: (),
    MeatProcessingRecord.DERIVED_PRODUCTS: (),
    MeatProcessingRecord.PACKAGING: (PackagingLabelStatus.UNLABELED,),
    MeatProcessingRecord.PRODUCED_LOTS: (
        ProcessingBatchStatus.PLANNED, ProcessingBatchStatus.IN_PROGRESS),
    MeatProcessingRecord.YIELDS: (
        YieldStatus.CRITICAL, YieldStatus.OUT_OF_TOLERANCE, YieldStatus.WARNING,
        YieldStatus.PENDING_REVIEW),
    MeatProcessingRecord.QUALITY: (
        OutputQualityStatus.PENDING_INSPECTION, OutputQualityStatus.QUARANTINED,
        OutputQualityStatus.REWORK_REQUIRED),
    MeatProcessingRecord.REWORK: (
        ReworkOrderStatus.CREATED, ReworkOrderStatus.APPROVED, ReworkOrderStatus.IN_PROGRESS),
    MeatProcessingRecord.INCIDENTS: (IncidentStatus.OPEN, IncidentStatus.UNDER_REVIEW),
    MeatProcessingRecord.AUDIT: (),
}


@dataclass(frozen=True, slots=True)
class _Consulta:
    columnas: tuple[tuple[str, str], ...]
    desde: str
    sucursal: str
    estado: str
    orden: str
    buscar_en: tuple[str, ...] = ()
    extra: str = ""
    extra_params: tuple = ()
    #: JOIN que sólo aporta el NOMBRE del producto. El listado lo usa; el conteo
    #: del badge no, así que contar no depende de la tabla de Productos.
    producto: str = ""


def _en(tipos) -> str:
    return ",".join("?" for _ in tipos)


_ORDEN = " JOIN processing_orders o ON o.id = {alias}.processing_order_id"
_PRODUCTO = " LEFT JOIN products p ON p.id = {columna}"
_OBJETIVO = _PRODUCTO.format(columna="o.target_product_id")

_SALIDAS = (
    ("id", "x.id"), ("produced_at", "x.produced_at"), ("process_type", "o.process_type"),
    ("product_name", "p.name"), ("output_type", "x.output_type"), ("quantity", "x.quantity"),
    ("weight", "x.weight"), ("unit", "x.unit"), ("quality_status", "x.quality_status"),
    ("lot_id", "x.lot_id"),
)
_DESDE_SALIDAS = "process_outputs x" + _ORDEN.format(alias="x")
_PRODUCTO_SALIDAS = _PRODUCTO.format(columna="x.product_id")

_ETIQUETADO = ("(CASE WHEN EXISTS (SELECT 1 FROM production_labels l"
               " WHERE l.packaging_execution_id = k.id AND l.printed_at IS NOT NULL)"
               " THEN 'LABELED' ELSE 'UNLABELED' END)")

_CONSULTAS: dict[MeatProcessingRecord, _Consulta] = {
    MeatProcessingRecord.PREPARATION: _Consulta(
        columnas=(
            ("id", "r.id"), ("created_at", "r.created_at"), ("process_type", "o.process_type"),
            ("order_status", "o.status"), ("product_name", "p.name"),
            ("required_quantity", "r.required_quantity"), ("required_weight", "r.required_weight"),
            ("reserved_weight", "r.reserved_weight"), ("consumed_weight", "r.consumed_weight"),
            ("unit", "r.unit"), ("status", "r.status"),
        ),
        desde="material_requirements r" + _ORDEN.format(alias="r"),
        producto=_PRODUCTO.format(columna="r.product_id"),
        sucursal="o.branch_id", estado="r.status", orden="r.created_at DESC, r.id DESC",
        buscar_en=("p.name",),
    ),
    MeatProcessingRecord.ACTIVE_PROCESSING: _Consulta(
        columnas=(
            ("id", "e.id"), ("process_type", "o.process_type"), ("product_name", "p.name"),
            ("status", "e.status"), ("started_at", "e.started_at"), ("paused_at", "e.paused_at"),
            ("total_paused_seconds", "e.total_paused_seconds"),
            ("planned_weight", "o.planned_weight"),
        ),
        desde="process_executions e" + _ORDEN.format(alias="e"), producto=_OBJETIVO,
        sucursal="o.branch_id", estado="e.status", orden="e.created_at DESC, e.id DESC",
        buscar_en=("p.name",),
    ),
    MeatProcessingRecord.WEIGHINGS: _Consulta(
        columnas=(
            ("id", "w.id"), ("captured_at", "w.captured_at"), ("process_type", "o.process_type"),
            ("product_name", "p.name"), ("weighing_type", "w.weighing_type"),
            ("gross_weight", "w.gross_weight"), ("tare_weight", "w.tare_weight"),
            ("unit", "w.unit"), ("stable", "w.stable"), ("manual_override", "w.manual_override"),
        ),
        desde="process_weighings w" + _ORDEN.format(alias="w"), producto=_OBJETIVO,
        sucursal="o.branch_id", estado="w.weighing_type", orden="w.captured_at DESC, w.id DESC",
        buscar_en=("p.name",),
    ),
    MeatProcessingRecord.CONSUMPTIONS: _Consulta(
        columnas=(
            ("id", "c.id"), ("created_at", "c.created_at"), ("process_type", "o.process_type"),
            ("product_name", "p.name"), ("lot_id", "c.lot_id"),
            ("planned_weight", "c.planned_weight"), ("actual_weight", "c.actual_weight"),
            ("unit", "c.unit"), ("status", "c.status"), ("consumed_at", "c.consumed_at"),
        ),
        desde="material_consumptions c" + _ORDEN.format(alias="c"),
        producto=_PRODUCTO.format(columna="c.product_id"),
        sucursal="o.branch_id", estado="c.status", orden="c.created_at DESC, c.id DESC",
        buscar_en=("p.name",),
    ),
    MeatProcessingRecord.CUTTING: _Consulta(
        columnas=_SALIDAS, desde=_DESDE_SALIDAS, producto=_PRODUCTO_SALIDAS,
        sucursal="o.branch_id",
        estado="x.output_type", orden="x.produced_at DESC, x.id DESC", buscar_en=("p.name",),
        extra=f"o.process_type IN ({_en(CUTTING_PROCESS_TYPES)})",
        extra_params=tuple(t.value for t in CUTTING_PROCESS_TYPES),
    ),
    MeatProcessingRecord.DERIVED_PRODUCTS: _Consulta(
        columnas=_SALIDAS, desde=_DESDE_SALIDAS, producto=_PRODUCTO_SALIDAS,
        sucursal="o.branch_id",
        estado="x.output_type", orden="x.produced_at DESC, x.id DESC", buscar_en=("p.name",),
        extra=f"o.process_type IN ({_en(DERIVED_PROCESS_TYPES)})",
        extra_params=tuple(t.value for t in DERIVED_PROCESS_TYPES),
    ),
    MeatProcessingRecord.PACKAGING: _Consulta(
        columnas=(
            ("id", "k.id"), ("packaged_at", "k.packaged_at"), ("product_name", "p.name"),
            ("lot_id", "k.lot_id"), ("package_quantity", "k.package_quantity"),
            ("net_weight", "k.net_weight"), ("expiration_date", "k.expiration_date"),
            ("labels", "(SELECT COUNT(*) FROM production_labels l WHERE l.packaging_execution_id = k.id)"),
            ("reprints", "(SELECT COALESCE(SUM(l.reprint_count), 0) FROM production_labels l"
                         " WHERE l.packaging_execution_id = k.id)"),
            ("status", _ETIQUETADO),
        ),
        desde="packaging_executions k" + _ORDEN.format(alias="k"),
        producto=_PRODUCTO.format(columna="k.product_id"),
        sucursal="o.branch_id", estado=_ETIQUETADO, orden="k.packaged_at DESC, k.id DESC",
        buscar_en=("p.name",),
    ),
    MeatProcessingRecord.PRODUCED_LOTS: _Consulta(
        columnas=(
            ("id", "b.id"), ("created_at", "b.created_at"), ("batch_number", "b.batch_number"),
            ("target_lot_code", "b.target_lot_code"), ("product_name", "p.name"),
            ("actual_quantity", "b.actual_quantity"), ("actual_weight", "b.actual_weight"),
            ("quality_status", "b.quality_status"), ("status", "b.status"),
            ("completed_at", "b.completed_at"),
        ),
        desde="processing_batches b" + _ORDEN.format(alias="b"), producto=_OBJETIVO,
        sucursal="o.branch_id", estado="b.status", orden="b.created_at DESC, b.id DESC",
        buscar_en=("b.batch_number", "b.target_lot_code", "p.name"),
    ),
    MeatProcessingRecord.YIELDS: _Consulta(
        columnas=(
            ("id", "y.id"), ("calculated_at", "y.calculated_at"),
            ("process_type", "o.process_type"), ("product_name", "p.name"),
            ("input_weight", "y.input_weight"),
            ("expected_output_weight", "y.expected_output_weight"),
            ("actual_output_weight", "y.actual_output_weight"), ("waste_weight", "y.waste_weight"),
            ("tolerance_pct", "y.tolerance_pct"), ("status", "y.status"),
        ),
        desde="yield_reconciliations y" + _ORDEN.format(alias="y"), producto=_OBJETIVO,
        sucursal="o.branch_id", estado="y.status", orden="y.calculated_at DESC, y.id DESC",
        buscar_en=("p.name",),
    ),
    MeatProcessingRecord.QUALITY: _Consulta(
        columnas=_SALIDAS, desde=_DESDE_SALIDAS, producto=_PRODUCTO_SALIDAS,
        sucursal="o.branch_id",
        estado="x.quality_status", orden="x.produced_at DESC, x.id DESC", buscar_en=("p.name",),
    ),
    MeatProcessingRecord.REWORK: _Consulta(
        columnas=(
            ("id", "r.id"), ("created_at", "r.created_at"), ("product_name", "p.name"),
            ("origin", "r.origin"), ("quantity", "r.quantity"), ("weight", "r.weight"),
            ("reason", "r.reason"), ("status", "r.status"),
        ),
        desde=("rework_orders r"
               " LEFT JOIN process_outputs so ON so.id = r.source_output_id"
               " JOIN processing_orders o"
               " ON o.id = COALESCE(r.processing_order_id, so.processing_order_id)"),
        producto=_PRODUCTO.format(columna="r.product_id"),
        sucursal="o.branch_id", estado="r.status", orden="r.created_at DESC, r.id DESC",
        buscar_en=("p.name", "r.reason"),
    ),
    MeatProcessingRecord.INCIDENTS: _Consulta(
        columnas=(
            ("id", "i.id"), ("reported_at", "i.reported_at"), ("incident_type", "i.incident_type"),
            ("process_type", "o.process_type"), ("description", "i.description"),
            ("status", "i.status"), ("resolved_at", "i.resolved_at"),
            ("resolution_notes", "i.resolution_notes"),
        ),
        desde="process_incidents i" + _ORDEN.format(alias="i"),
        sucursal="o.branch_id", estado="i.status", orden="i.reported_at DESC, i.id DESC",
        buscar_en=("i.description", "i.resolution_notes"),
    ),
    MeatProcessingRecord.AUDIT: _Consulta(
        columnas=(
            ("id", "a.id"), ("occurred_at", "a.occurred_at"), ("user_id", "a.user_id"),
            ("entity_type", "a.entity_type"), ("action", "a.action"),
            ("entity_id", "a.entity_id"), ("reason", "a.reason"),
        ),
        desde="meat_processing_audit_log a",
        sucursal="a.branch_id", estado="a.entity_type", orden="a.occurred_at DESC, a.id DESC",
        buscar_en=("a.action", "a.entity_id", "a.user_id", "a.reason"),
    ),
}

SEARCHABLE_RECORDS = frozenset(r for r, c in _CONSULTAS.items() if c.buscar_en)


@dataclass(frozen=True, slots=True)
class MeatProcessingRecordPage:
    rows: list[dict]
    total: int


class MeatProcessingRecordsQueryService:
    def __init__(self, db) -> None:
        self.db = db

    def list_records(
        self, branch_id: str, record: MeatProcessingRecord, *, status: str | None = None,
        query: str = "", page: int = 0, page_size: int = 50,
    ) -> MeatProcessingRecordPage:
        """Un registro de la sucursal, lo que pide atención primero. Un `status`
        que no es del enum del registro se rechaza (`ValueError`) en vez de dar una
        lista vacía que parezca "no hay nada"."""
        record = MeatProcessingRecord(record)
        consulta = _CONSULTAS[record]
        where, valores = self._where(consulta, record, branch_id, status, query)
        desde = consulta.desde + consulta.producto

        total = self.db.execute(
            f"SELECT COUNT(*) FROM {desde} WHERE {where}", valores).fetchone()[0]

        atencion = ATTENTION[record]
        orden, orden_valores = consulta.orden, []
        if atencion:
            orden = (f"CASE WHEN {consulta.estado} IN ({_en(atencion)}) THEN 0 ELSE 1 END,"
                     f" {orden}")
            orden_valores = [estado.value for estado in atencion]
        select = ", ".join(expr for _, expr in consulta.columnas)
        filas = self.db.execute(
            f"SELECT {select} FROM {desde} WHERE {where} ORDER BY {orden}"
            " LIMIT ? OFFSET ?",
            [*valores, *orden_valores, page_size, page * page_size]).fetchall()
        nombres = [nombre for nombre, _ in consulta.columnas]
        return MeatProcessingRecordPage(
            rows=[dict(zip(nombres, fila)) for fila in filas], total=total)

    def count_needing_attention(self, branch_id: str, record: MeatProcessingRecord) -> int:
        """Lo que cuenta el badge: los estados "por atender" del MISMO registro."""
        record = MeatProcessingRecord(record)
        consulta = _CONSULTAS[record]
        atencion = ATTENTION[record]
        if not atencion:
            raise ValueError(f"El registro {record.value} no tiene estados por atender")
        where, valores = self._where(consulta, record, branch_id, None, "")
        return self.db.execute(
            f"SELECT COUNT(*) FROM {consulta.desde} WHERE {where}"
            f" AND {consulta.estado} IN ({_en(atencion)})",
            [*valores, *(estado.value for estado in atencion)]).fetchone()[0]

    @staticmethod
    def _where(consulta: _Consulta, record, branch_id, status, query):
        where = [f"{consulta.sucursal}=?"]
        valores: list = [branch_id]
        if consulta.extra:
            where.append(f"({consulta.extra})")
            valores += list(consulta.extra_params)
        if status:
            where.append(f"{consulta.estado}=?")
            valores.append(STATUS_ENUM[record](status).value)
        if query:
            if not consulta.buscar_en:
                raise ValueError(f"El registro {record.value} no admite búsqueda")
            where.append("(" + " OR ".join(f"{c} LIKE ?" for c in consulta.buscar_en) + ")")
            valores += [f"%{query}%"] * len(consulta.buscar_en)
        return " AND ".join(where), valores
