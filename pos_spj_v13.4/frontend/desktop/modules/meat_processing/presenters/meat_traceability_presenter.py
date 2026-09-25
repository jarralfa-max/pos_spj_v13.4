"""MeatTraceabilityPresenter (Trazabilidad) — formato del recorrido de un lote.

No arma SQL ni recorre el grafo: `MeatLotTraceabilityQueryService` compone los
lotes producidos por la sucursal con la trazabilidad de Inventario, que es quien
guarda la genealogía de lotes.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation

from backend.application.meat_processing.queries.lot_traceability_query_service import (
    MeatLotTraceabilityQueryService,
)
from frontend.desktop.components.search_selector import SearchOption
from frontend.desktop.modules.meat_processing.presenters.meat_processing_record_presenter import (
    PROCESS_TYPE_LABELS,
)

#: Movimientos del libro de Inventario, en el idioma del operador.
#: Tipo de documento origen de un movimiento, como lo entiende quien opera.
DOCUMENT_LABELS: dict[str, str] = {
    "SALE": "Venta", "SALE_RETURN": "Devolución de venta", "SALE_REVERSAL": "Reverso de venta",
    "PURCHASE": "Compra", "PURCHASE_RETURN": "Devolución a proveedor",
    "RECETA_COMPRA": "Compra (receta)", "TRANSFER": "Transferencia",
    "PROCESSING_ORDER": "Orden de producción", "PRODUCTION_ORDER": "Orden de producción",
    "PRODUCTION": "Producción", "RECONSTRUCTION": "Reconstrucción",
    "LOSS_CASE": "Merma", "EXPIRY": "Caducidad", "ADJUSTMENT": "Ajuste",
    "REVERSAL": "Reverso", "QUARANTINE": "Cuarentena",
    "QUARANTINE_DISPOSAL": "Baja desde cuarentena", "LOT_QUALITY": "Calidad del lote",
    "INSPECTION": "Inspección",
}

MOVEMENT_LABELS: dict[str, str] = {
    "PURCHASE_RECEIPT": "Compra recibida", "DIRECT_PURCHASE_RECEIPT": "Compra directa",
    "SALE_ISSUE": "Venta", "SALE_RETURN": "Devolución de venta",
    "TRANSFER_DISPATCH": "Transferencia enviada", "TRANSFER_RECEIPT": "Transferencia recibida",
    "PRODUCTION_CONSUMPTION": "Consumo de producción", "PRODUCTION_OUTPUT": "Salida de producción",
    "SLAUGHTER_INPUT_FUTURE": "Entrada de sacrificio", "SLAUGHTER_OUTPUT_FUTURE": "Salida de sacrificio",
    "KIT_ASSEMBLY": "Armado de kit", "KIT_DISASSEMBLY": "Desarmado de kit",
    "QUALITY_BLOCK": "Bloqueo de calidad", "QUALITY_RELEASE": "Liberación de calidad",
    "QUARANTINE_ENTRY": "Entrada a cuarentena", "QUARANTINE_RELEASE": "Salida de cuarentena",
    "EXPIRY_STATUS_TRANSFER": "Cambio por caducidad", "ADJUSTMENT_IN": "Ajuste de entrada",
    "ADJUSTMENT_OUT": "Ajuste de salida", "COUNT_VARIANCE": "Diferencia de conteo",
    "WASTE": "Desperdicio", "SHRINKAGE": "Merma",
    "CUSTOMER_RETURN": "Devolución de cliente", "SUPPLIER_RETURN": "Devolución a proveedor",
    "EXPIRY_DISPOSAL": "Baja por caducidad", "REVERSAL": "Reverso",
}


@dataclass(slots=True)
class TraceTableModel:
    rows: list[list[str]] = field(default_factory=list)
    row_ids: list[str] = field(default_factory=list)


@dataclass(slots=True)
class LotTraceViewModel:
    """Lo que la pantalla pinta de un lote: un resumen y dos tablas."""

    summary: str = ""
    origin: str = ""
    inputs: TraceTableModel = field(default_factory=TraceTableModel)
    destinations: TraceTableModel = field(default_factory=TraceTableModel)
    chained: TraceTableModel = field(default_factory=TraceTableModel)


def _texto(valor, vacio: str = "—") -> str:
    return str(valor) if valor not in (None, "") else vacio


def _codigo(valor) -> str:
    """El código de un lote tal como lo registró Inventario; nunca su identidad."""
    return str(valor) if valor else "Sin código"


def _fecha(valor) -> str:
    return str(valor)[:16].replace("T", " ") if valor else "—"


def _peso(valor) -> str:
    try:
        numero = Decimal(str(valor or "0"))
    except InvalidOperation:
        return _texto(valor)
    return f"{numero.normalize():f} kg" if numero else "—"


class MeatTraceabilityPresenter:
    def __init__(self, connection, *, branch_id: str,
                 service_factory=MeatLotTraceabilityQueryService) -> None:
        self._conn = connection
        self._branch_id = branch_id
        self._service_factory = service_factory

    def search_lots(self, query: str) -> list[SearchOption]:
        lotes = self._service_factory(self._conn).search_lots(
            self._branch_id, query=query or "")
        return [
            SearchOption(
                lote.lot_id, _codigo(lote.lot_code),
                f"{_texto(lote.product_name)} · {_peso(lote.weight)} · {_fecha(lote.produced_at)}")
            for lote in lotes
        ]

    def trace(self, lot_id: str) -> LotTraceViewModel:
        """Vacío si el lote no lo produjo esta sucursal: la pantalla lo dice en vez
        de enseñar la producción de otra."""
        if not lot_id:
            return LotTraceViewModel()
        recorrido = self._service_factory(self._conn).trace(self._branch_id, lot_id)
        if recorrido is None:
            return LotTraceViewModel(
                summary="Ese lote no lo produjo esta sucursal.")
        lote = recorrido.produced
        alcanzados = len(recorrido.affected_lots)
        destino = ("Llegó a clientes" if recorrido.reaches_customers
                   else "Sin ventas registradas")
        return LotTraceViewModel(
            summary=(f"{_texto(lote.product_name)} · {_peso(lote.weight)} · "
                     f"{PROCESS_TYPE_LABELS.get(lote.process_type, _texto(lote.process_type))} · "
                     f"{lote.order_folio or 'orden sin folio'} · "
                     f"producido {_fecha(lote.produced_at)}"),
            origin=(f"{destino} · {alcanzados} lote(s) alcanzado(s) · "
                    f"{len(recorrido.branches_touched)} sucursal(es)"),
            inputs=TraceTableModel(
                rows=[[_codigo(entrada.lot_code), _texto(entrada.product_name),
                       _peso(entrada.weight)] for entrada in recorrido.inputs],
                row_ids=[entrada.lot_id for entrada in recorrido.inputs]),
            chained=TraceTableModel(
                rows=[[c.order_folio or f"Orden del {_fecha(c.order_created_at)}",
                       PROCESS_TYPE_LABELS.get(c.process_type, _texto(c.process_type)),
                       _texto(c.product_name), _peso(c.weight), _fecha(c.linked_at)]
                      for c in recorrido.chained],
                row_ids=[c.processing_order_id for c in recorrido.chained]),
            destinations=TraceTableModel(
                rows=[[_fecha(d.occurred_at),
                       MOVEMENT_LABELS.get(d.movement_type, _texto(d.movement_type)),
                       _texto(d.source_module),
                       DOCUMENT_LABELS.get(d.source_document_type, _texto(d.source_document_type)),
                       _texto(d.branch_name) or "Sucursal no registrada", _peso(d.weight)]
                      for d in recorrido.destinations],
                row_ids=[f"{d.source_document_id}-{d.occurred_at}"
                         for d in recorrido.destinations]),
        )
