"""MeatProcessingRecordPresenter (PASS 6) — los registros de Procesamiento Cárnico.

No arma SQL: pide la página a `MeatProcessingRecordsQueryService` y le da formato.
Las etiquetas de estado viven aquí y la página arma su filtro con ellas: el combo y
la columna no pueden llamar distinto al mismo estado.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation

from backend.application.meat_processing.queries.meat_processing_records_query_service import (
    MeatProcessingRecord,
    MeatProcessingRecordsQueryService,
)

@dataclass(slots=True)
class MeatRecordTableModel:
    """Filas ya formateadas, sus ids y el total que cumple el filtro (no el de
    la página): `WorklistPage.set_table` pagina con él."""

    rows: list[list[str]] = field(default_factory=list)
    row_ids: list[str] = field(default_factory=list)
    total: int = 0


PROCESS_TYPE_LABELS: dict[str, str] = {
    "CUTTING": "Corte", "DISASSEMBLY": "Despiece", "DEBONING": "Deshuese",
    "TRIMMING": "Limpieza", "PORTIONING": "Porcionado", "GRINDING": "Molido",
    "MIXING": "Mezclado", "MARINATION": "Marinado", "FORMULATION": "Formulación",
    "PACKAGING": "Empaque", "REPACKAGING": "Reempaque", "LABELING": "Etiquetado",
    "FREEZING": "Congelado", "THAWING": "Descongelado", "CHILLING": "Enfriado",
}

INCIDENT_TYPE_LABELS: dict[str, str] = {
    "EQUIPMENT_FAILURE": "Falla de equipo", "MATERIAL_SHORTAGE": "Faltante de material",
    "QUALITY_ISSUE": "Problema de calidad", "TEMPERATURE_DEVIATION": "Desviación de temperatura",
    "WEIGHT_VARIANCE": "Variación de peso", "OPERATOR_ERROR": "Error de operario",
    "RECIPE_ERROR": "Error de receta", "PACKAGING_FAILURE": "Falla de empaque",
    "POWER_FAILURE": "Falla eléctrica", "NETWORK_FAILURE": "Falla de red",
    "SAFETY_EVENT": "Evento de seguridad", "OTHER": "Otro",
}

REWORK_ORIGIN_LABELS: dict[str, str] = {
    "QUALITY_DECISION": "Decisión de calidad", "PROCESSING_INCIDENT": "Incidencia de proceso",
    "OUTPUT_VARIANCE": "Variación de salida", "PACKAGING_FAILURE": "Falla de empaque",
    "CUSTOMER_RETURN_AUTHORIZED": "Devolución autorizada",
}

_OUTPUT_TYPES = {
    "MAIN_PRODUCT": "Producto principal", "CO_PRODUCT": "Coproducto",
    "BY_PRODUCT": "Subproducto", "SEMI_FINISHED": "Semiterminado",
    "WORK_IN_PROGRESS": "En proceso", "REWORKABLE": "Reprocesable",
    "WASTE": "Desperdicio", "LOSS": "Merma",
}

STATUS_LABELS: dict[MeatProcessingRecord, dict[str, str]] = {
    MeatProcessingRecord.PREPARATION: {
        "REQUIRED": "Requerido", "RESERVED": "Reservado", "ALLOCATED": "Asignado",
        "CONSUMED": "Consumido", "CANCELLED": "Cancelado",
    },
    MeatProcessingRecord.ACTIVE_PROCESSING: {
        "NOT_STARTED": "Sin iniciar", "ACTIVE": "En curso", "PAUSED": "En pausa",
        "COMPLETED": "Completada", "CANCELLED": "Cancelada", "FAILED": "Fallida",
    },
    MeatProcessingRecord.WEIGHINGS: {
        "INPUT": "Entrada", "INTERMEDIATE": "Intermedio", "OUTPUT": "Salida",
        "CO_PRODUCT": "Coproducto", "BY_PRODUCT": "Subproducto", "WASTE": "Desperdicio",
        "REWORK": "Reproceso", "CARCASS_FUTURE": "Canal (futuro)",
    },
    MeatProcessingRecord.CONSUMPTIONS: {
        "DRAFT": "Borrador", "PENDING_POSTING": "Por aplicar", "POSTED": "Aplicado",
        "REVERSED": "Revertido",
    },
    MeatProcessingRecord.CUTTING: _OUTPUT_TYPES,
    MeatProcessingRecord.DERIVED_PRODUCTS: _OUTPUT_TYPES,
    MeatProcessingRecord.PACKAGING: {"UNLABELED": "Sin etiqueta", "LABELED": "Etiquetado"},
    MeatProcessingRecord.PRODUCED_LOTS: {
        "PLANNED": "Planeado", "IN_PROGRESS": "En proceso", "COMPLETED": "Completado",
        "CANCELLED": "Cancelado",
    },
    MeatProcessingRecord.YIELDS: {
        "WITHIN_TOLERANCE": "Dentro de tolerancia", "WARNING": "Advertencia",
        "OUT_OF_TOLERANCE": "Fuera de tolerancia", "CRITICAL": "Crítico",
        "PENDING_REVIEW": "Por revisar", "APPROVED": "Aprobado",
    },
    MeatProcessingRecord.QUALITY: {
        "PENDING_INSPECTION": "Por inspeccionar", "QUARANTINED": "En cuarentena",
        "RELEASED": "Liberado", "REJECTED": "Rechazado",
        "REWORK_REQUIRED": "Requiere reproceso", "CONDEMNED": "Decomisado",
    },
    MeatProcessingRecord.REWORK: {
        "CREATED": "Creado", "APPROVED": "Aprobado", "IN_PROGRESS": "En proceso",
        "COMPLETED": "Completado", "CLOSED": "Cerrado", "CANCELLED": "Cancelado",
    },
    MeatProcessingRecord.INCIDENTS: {
        "OPEN": "Abierta", "UNDER_REVIEW": "En revisión", "RESOLVED": "Resuelta",
        "CLOSED": "Cerrada",
    },
    MeatProcessingRecord.AUDIT: {
        "ProcessingOrder": "Orden", "MaterialRequirement": "Requerimiento",
        "MaterialConsumption": "Consumo", "ProcessOutput": "Salida",
        "YieldReconciliation": "Rendimiento", "ProcessIncident": "Incidencia",
        "ReworkOrder": "Reproceso", "OperatorAssignment": "Asignación de operario",
        "EquipmentAssignment": "Asignación de equipo", "ProductionEquipment": "Equipo",
        "ProductionAlert": "Alerta",
    },
}


def _texto(valor, vacio: str = "—") -> str:
    return str(valor) if valor not in (None, "") else vacio


def _corto(valor) -> str:
    return str(valor)[:8] if valor else "—"


def _fecha(valor) -> str:
    return str(valor)[:16].replace("T", " ") if valor else "—"


def _decimal(valor) -> Decimal | None:
    if valor in (None, ""):
        return None
    try:
        return Decimal(str(valor))
    except InvalidOperation:
        return None


def _numero(valor) -> str:
    numero = _decimal(valor)
    if numero is None:
        return "—"
    return format(numero.normalize(), "f") if numero == numero.to_integral() else f"{numero:.3f}"


def _si_no(valor) -> str:
    return "Sí" if valor in (1, True, "1") else "No"


def _proceso(valor) -> str:
    return PROCESS_TYPE_LABELS.get(valor, _texto(valor))


def _variacion(esperado, real) -> str:
    esperado, real = _decimal(esperado), _decimal(real)
    if not esperado or real is None:
        return "—"
    pct = (real - esperado) / esperado * Decimal("100")
    return f"{'+' if pct > 0 else ''}{pct:.1f}%"


def _minutos(segundos) -> str:
    numero = _decimal(segundos)
    return f"{(numero / Decimal('60')):.0f} min" if numero else "—"


def _fila_preparacion(f, estados):
    return [_fecha(f["created_at"]), _proceso(f["process_type"]), _texto(f["product_name"]),
            _numero(f["required_weight"]), _numero(f["reserved_weight"]),
            _numero(f["consumed_weight"]), _texto(f["unit"]), estados.get(f["status"], f["status"])]


def _fila_ejecucion(f, estados):
    return [_proceso(f["process_type"]), _texto(f["product_name"]),
            estados.get(f["status"], f["status"]), _fecha(f["started_at"]),
            _fecha(f["paused_at"]), _minutos(f["total_paused_seconds"]),
            _numero(f["planned_weight"])]


def _fila_pesaje(f, estados):
    bruto, tara = _decimal(f["gross_weight"]), _decimal(f["tare_weight"]) or Decimal("0")
    return [_fecha(f["captured_at"]), _proceso(f["process_type"]), _texto(f["product_name"]),
            estados.get(f["weighing_type"], f["weighing_type"]), _numero(bruto), _numero(tara),
            _numero(bruto - tara) if bruto is not None else "—", _texto(f["unit"]),
            _si_no(f["stable"]), _si_no(f["manual_override"])]


def _fila_consumo(f, estados):
    return [_fecha(f["created_at"]), _proceso(f["process_type"]), _texto(f["product_name"]),
            _corto(f["lot_id"]), _numero(f["planned_weight"]), _numero(f["actual_weight"]),
            _texto(f["unit"]), estados.get(f["status"], f["status"])]


def _fila_salida(f, _estados):
    calidad = STATUS_LABELS[MeatProcessingRecord.QUALITY]
    return [_fecha(f["produced_at"]), _proceso(f["process_type"]), _texto(f["product_name"]),
            _OUTPUT_TYPES.get(f["output_type"], f["output_type"]), _numero(f["quantity"]),
            _numero(f["weight"]), _texto(f["unit"]),
            calidad.get(f["quality_status"], f["quality_status"]), _corto(f["lot_id"])]


def _fila_empaque(f, estados):
    return [_fecha(f["packaged_at"]), _texto(f["product_name"]), _corto(f["lot_id"]),
            _texto(f["package_quantity"]), _numero(f["net_weight"]),
            _fecha(f["expiration_date"]), str(f["labels"]), str(f["reprints"]),
            estados.get(f["status"], f["status"])]


def _fila_lote(f, estados):
    return [_fecha(f["created_at"]), _texto(f["batch_number"]), _texto(f["target_lot_code"]),
            _texto(f["product_name"]), _numero(f["actual_quantity"]),
            _numero(f["actual_weight"]), _texto(f["quality_status"]),
            estados.get(f["status"], f["status"])]


def _fila_rendimiento(f, estados):
    return [_fecha(f["calculated_at"]), _proceso(f["process_type"]), _texto(f["product_name"]),
            _numero(f["input_weight"]), _numero(f["expected_output_weight"]),
            _numero(f["actual_output_weight"]), _numero(f["waste_weight"]),
            _variacion(f["expected_output_weight"], f["actual_output_weight"]),
            f"{_numero(f['tolerance_pct'])}%", estados.get(f["status"], f["status"])]


def _fila_reproceso(f, estados):
    return [_fecha(f["created_at"]), _texto(f["product_name"]),
            REWORK_ORIGIN_LABELS.get(f["origin"], _texto(f["origin"])), _numero(f["quantity"]),
            _numero(f["weight"]), _texto(f["reason"]), estados.get(f["status"], f["status"])]


def _fila_incidencia(f, estados):
    return [_fecha(f["reported_at"]),
            INCIDENT_TYPE_LABELS.get(f["incident_type"], _texto(f["incident_type"])),
            _proceso(f["process_type"]), _texto(f["description"]),
            estados.get(f["status"], f["status"]), _fecha(f["resolved_at"]),
            _texto(f["resolution_notes"])]


def _fila_auditoria(f, estados):
    return [_fecha(f["occurred_at"]), _corto(f["user_id"]),
            estados.get(f["entity_type"], _texto(f["entity_type"])), _texto(f["action"]),
            _corto(f["entity_id"]), _texto(f["reason"])]


_FORMATO = {
    MeatProcessingRecord.PREPARATION: _fila_preparacion,
    MeatProcessingRecord.ACTIVE_PROCESSING: _fila_ejecucion,
    MeatProcessingRecord.WEIGHINGS: _fila_pesaje,
    MeatProcessingRecord.CONSUMPTIONS: _fila_consumo,
    MeatProcessingRecord.CUTTING: _fila_salida,
    MeatProcessingRecord.DERIVED_PRODUCTS: _fila_salida,
    MeatProcessingRecord.PACKAGING: _fila_empaque,
    MeatProcessingRecord.PRODUCED_LOTS: _fila_lote,
    MeatProcessingRecord.YIELDS: _fila_rendimiento,
    MeatProcessingRecord.QUALITY: _fila_salida,
    MeatProcessingRecord.REWORK: _fila_reproceso,
    MeatProcessingRecord.INCIDENTS: _fila_incidencia,
    MeatProcessingRecord.AUDIT: _fila_auditoria,
}


class MeatProcessingRecordPresenter:
    def __init__(self, connection, *, branch_id: str, record: MeatProcessingRecord,
                 page_size: int = 50) -> None:
        self._conn = connection
        self._branch_id = branch_id
        self._record = MeatProcessingRecord(record)
        self._page_size = page_size

    @property
    def record(self) -> MeatProcessingRecord:
        return self._record

    def rows(self, *, query: str = "", status: str | None = None, page: int = 0):
        pagina = MeatProcessingRecordsQueryService(self._conn).list_records(
            self._branch_id, self._record, status=status, query=query, page=page,
            page_size=self._page_size)
        formato = _FORMATO[self._record]
        estados = STATUS_LABELS[self._record]
        return MeatRecordTableModel(
            rows=[formato(fila, estados) for fila in pagina.rows],
            row_ids=[fila["id"] for fila in pagina.rows], total=pagina.total)
