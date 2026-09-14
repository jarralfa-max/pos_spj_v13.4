"""Páginas de registros de Procesamiento Cárnico (PASS 6).

`MeatProcessingRecordPage` es una sola clase para todos los registros: las columnas
dependen del registro y el orden de cada fila lo decide el presenter. Filtro por
estado siempre; búsqueda donde la consulta tiene texto que buscar.

"Pesajes y consumos" es UNA ruta con DOS registros de distinta forma (un pesaje no
tiene insumo ni lote; un consumo no tiene tara), así que va en pestañas en vez de
mezclarlos en una tabla con la mitad de las columnas vacías.
"""

from __future__ import annotations

from backend.application.meat_processing.queries.meat_processing_records_query_service import (
    SEARCHABLE_RECORDS,
    MeatProcessingRecord,
)
from frontend.desktop.components.pages import TabbedPage
from frontend.desktop.components.tables import ColumnSpec
from frontend.desktop.components.worklist_page import WorklistPage
from frontend.desktop.modules.meat_processing.presenters.meat_processing_record_presenter import (
    STATUS_LABELS,
)

_SALIDAS = [
    ColumnSpec("Fecha", "date"), ColumnSpec("Proceso"), ColumnSpec("Producto"),
    ColumnSpec("Tipo de salida", "status"), ColumnSpec("Cantidad", "numeric"),
    ColumnSpec("Peso", "numeric"), ColumnSpec("Unidad"), ColumnSpec("Calidad", "status"),
    ColumnSpec("Lote"),
]

COLUMNS: dict[MeatProcessingRecord, list[ColumnSpec]] = {
    MeatProcessingRecord.PREPARATION: [
        ColumnSpec("Fecha", "date"), ColumnSpec("Proceso"), ColumnSpec("Insumo"),
        ColumnSpec("Requerido", "numeric"), ColumnSpec("Reservado", "numeric"),
        ColumnSpec("Consumido", "numeric"), ColumnSpec("Unidad"), ColumnSpec("Estado", "status"),
    ],
    MeatProcessingRecord.ACTIVE_PROCESSING: [
        ColumnSpec("Proceso"), ColumnSpec("Producto"), ColumnSpec("Estado", "status"),
        ColumnSpec("Inicio", "date"), ColumnSpec("En pausa desde", "date"),
        ColumnSpec("Tiempo en pausa"), ColumnSpec("Peso planeado", "numeric"),
    ],
    MeatProcessingRecord.WEIGHINGS: [
        ColumnSpec("Fecha", "date"), ColumnSpec("Proceso"), ColumnSpec("Producto"),
        ColumnSpec("Tipo", "status"), ColumnSpec("Bruto", "numeric"), ColumnSpec("Tara", "numeric"),
        ColumnSpec("Neto", "numeric"), ColumnSpec("Unidad"), ColumnSpec("Estable"),
        ColumnSpec("Manual"),
    ],
    MeatProcessingRecord.CONSUMPTIONS: [
        ColumnSpec("Fecha", "date"), ColumnSpec("Proceso"), ColumnSpec("Insumo"),
        ColumnSpec("Lote"), ColumnSpec("Planeado", "numeric"), ColumnSpec("Real", "numeric"),
        ColumnSpec("Unidad"), ColumnSpec("Estado", "status"),
    ],
    MeatProcessingRecord.CUTTING: _SALIDAS,
    MeatProcessingRecord.DERIVED_PRODUCTS: _SALIDAS,
    MeatProcessingRecord.QUALITY: _SALIDAS,
    MeatProcessingRecord.PACKAGING: [
        ColumnSpec("Empacado", "date"), ColumnSpec("Producto"), ColumnSpec("Lote"),
        ColumnSpec("Paquetes", "numeric"), ColumnSpec("Peso neto", "numeric"),
        ColumnSpec("Caducidad", "date"), ColumnSpec("Etiquetas", "numeric"),
        ColumnSpec("Reimpresiones", "numeric"), ColumnSpec("Estado", "status"),
    ],
    MeatProcessingRecord.PRODUCED_LOTS: [
        ColumnSpec("Creado", "date"), ColumnSpec("Lote"), ColumnSpec("Código de lote"),
        ColumnSpec("Producto"), ColumnSpec("Cantidad", "numeric"), ColumnSpec("Peso", "numeric"),
        ColumnSpec("Calidad", "status"), ColumnSpec("Estado", "status"),
    ],
    MeatProcessingRecord.YIELDS: [
        ColumnSpec("Fecha", "date"), ColumnSpec("Proceso"), ColumnSpec("Producto"),
        ColumnSpec("Entrada", "numeric"), ColumnSpec("Esperado", "numeric"),
        ColumnSpec("Real", "numeric"), ColumnSpec("Merma", "numeric"),
        ColumnSpec("Variación", "numeric"), ColumnSpec("Tolerancia"), ColumnSpec("Estado", "status"),
    ],
    MeatProcessingRecord.REWORK: [
        ColumnSpec("Fecha", "date"), ColumnSpec("Producto"), ColumnSpec("Origen"),
        ColumnSpec("Cantidad", "numeric"), ColumnSpec("Peso", "numeric"), ColumnSpec("Motivo"),
        ColumnSpec("Estado", "status"),
    ],
    MeatProcessingRecord.INCIDENTS: [
        ColumnSpec("Fecha", "date"), ColumnSpec("Tipo"), ColumnSpec("Proceso"),
        ColumnSpec("Descripción"), ColumnSpec("Estado", "status"), ColumnSpec("Resuelta", "date"),
        ColumnSpec("Resolución"),
    ],
    MeatProcessingRecord.AUDIT: [
        ColumnSpec("Fecha", "date"), ColumnSpec("Usuario"), ColumnSpec("Entidad", "status"),
        ColumnSpec("Acción"), ColumnSpec("Identificador"), ColumnSpec("Motivo"),
    ],
}


class MeatProcessingRecordPage(WorklistPage):
    paginated = True

    def __init__(self, presenter, *, title: str, subtitle: str, empty_message: str,
                 parent=None) -> None:
        record = presenter.record
        # La base lee todo esto dentro de su `__init__`.
        self.title = title
        self.subtitle = subtitle
        self.empty_message = empty_message
        self.columns = COLUMNS[record]
        self.searchable = record in SEARCHABLE_RECORDS
        self.status_filter = list(STATUS_LABELS[record].items())
        super().__init__(presenter, parent)
        self.setAccessibleName(title)
        self.setAccessibleDescription(subtitle)

    def _load(self) -> None:
        self.set_table(self._presenter.rows(
            query=self._search.query() if self.searchable else "",
            status=self._status_id(), page=self._page))


class WeighingsAndConsumptionsPage(TabbedPage):
    """Pesajes y consumos: dos registros, una pestaña cada uno."""

    def __init__(self, weighings: MeatProcessingRecordPage,
                 consumptions: MeatProcessingRecordPage, *, title: str, subtitle: str,
                 parent=None) -> None:
        super().__init__(parent, title=title, subtitle=subtitle)
        self.title = title
        self.weighings = weighings
        self.consumptions = consumptions
        self.tabs.addTab(weighings, "Pesajes")
        self.tabs.addTab(consumptions, "Consumos")
        self.setAccessibleName(title)
        self.setAccessibleDescription(subtitle)

    def ensure_loaded(self) -> None:
        self.weighings.ensure_loaded()
        self.consumptions.ensure_loaded()
