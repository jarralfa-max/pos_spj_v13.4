"""DeliveryRecordPage (PASS 6) — un registro de reparto: reentregas, cobros en
ruta, liquidaciones o rutas.

Una sola clase; las columnas dependen del registro y el orden de cada fila lo
decide el presenter. Filtro por estado siempre; búsqueda sólo donde la consulta
tiene texto que buscar (`SEARCHABLE_RECORDS`).
"""

from __future__ import annotations

from backend.application.orders_delivery.queries.delivery_records_query_service import (
    SEARCHABLE_RECORDS,
    DeliveryRecord,
)
from frontend.desktop.components.tables import ColumnSpec
from frontend.desktop.components.worklist_page import WorklistPage
from frontend.desktop.modules.orders_delivery.presenters.delivery_record_presenter import (
    STATUS_LABELS,
)

COLUMNS: dict[DeliveryRecord, list[ColumnSpec]] = {
    DeliveryRecord.REDELIVERIES: [
        ColumnSpec("Solicitada", "date"), ColumnSpec("Entrega original"),
        ColumnSpec("Pedido"), ColumnSpec("Cliente"), ColumnSpec("Motivo"),
        ColumnSpec("Cargo adicional", "numeric"), ColumnSpec("Estado", "status"),
        ColumnSpec("Nueva entrega"),
    ],
    DeliveryRecord.CASH_COLLECTIONS: [
        ColumnSpec("Entrega"), ColumnSpec("Pedido"), ColumnSpec("Cliente"),
        ColumnSpec("Repartidor"), ColumnSpec("Método"),
        ColumnSpec("Esperado", "numeric"), ColumnSpec("Cobrado", "numeric"),
        ColumnSpec("Estado", "status"), ColumnSpec("Cobrado el", "date"),
    ],
    DeliveryRecord.SETTLEMENTS: [
        ColumnSpec("Creada", "date"), ColumnSpec("Repartidor"),
        ColumnSpec("Cobros", "numeric"), ColumnSpec("Esperado", "numeric"),
        ColumnSpec("Entregado", "numeric"), ColumnSpec("Diferencia", "numeric"),
        ColumnSpec("Estado", "status"),
    ],
    DeliveryRecord.ROUTES: [
        ColumnSpec("Ruta"), ColumnSpec("Estado", "status"), ColumnSpec("Repartidor"),
        ColumnSpec("Paradas", "numeric"), ColumnSpec("Creada", "date"),
        ColumnSpec("Actualización", "date"),
    ],
}


class DeliveryRecordPage(WorklistPage):
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
        model = self._presenter.rows(
            query=self._search.query() if self.searchable else "",
            status=self._status_id(), page=self._page)
        self.set_table(model)
