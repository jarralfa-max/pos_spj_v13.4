"""DeliveryJobWorklistPage (PASS 6) — una bandeja de reparto: búsqueda, tabla y
paginación sobre un filtro FIJO de estados de `delivery_jobs`.

Una sola clase para las cuatro bandejas de reparto; qué trabajos entran lo decide
`delivery_worklists`, no la vista. La columna "Motivo" muestra el último intento
fallido, que es lo que explica por qué una entrega está donde está.
"""

from __future__ import annotations

from frontend.desktop.components.tables import ColumnSpec
from frontend.desktop.components.worklist_page import WorklistPage


class DeliveryJobWorklistPage(WorklistPage):
    searchable = True
    paginated = True
    status_filter: list[tuple] = []
    columns = [
        ColumnSpec("Entrega"),
        ColumnSpec("Pedido"),
        ColumnSpec("Cliente"),
        ColumnSpec("Estado", "status"),
        ColumnSpec("Repartidor"),
        ColumnSpec("Motivo"),
        ColumnSpec("Actualización", "date"),
    ]

    def __init__(self, presenter, *, title: str, subtitle: str, empty_message: str,
                 parent=None) -> None:
        # La base lee título, subtítulo y mensaje vacío dentro de su `__init__`.
        self.title = title
        self.subtitle = subtitle
        self.empty_message = empty_message
        super().__init__(presenter, parent)
        self.setAccessibleName(title)
        self.setAccessibleDescription(subtitle)

    def _load(self) -> None:
        model = self._presenter.jobs(
            query=self._search.query() if self.searchable else "", page=self._page)
        self.set_table(model)
