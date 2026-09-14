"""OrderWorklistPage (PASS 6) — una bandeja de pedidos: búsqueda, tabla y
paginación sobre un filtro FIJO.

No hay combo de estados: la bandeja ya ES el filtro. Una sola clase para las seis
bandejas, porque lo que cambia entre ellas es qué pedidos entran, y eso lo decide
`order_worklists`, no la vista. Las columnas son las de "Todos los pedidos", para
que un pedido se lea igual esté donde esté.
"""

from __future__ import annotations

from frontend.desktop.components.worklist_page import WorklistPage
from frontend.desktop.modules.orders_delivery.pages.orders_list_page import OrdersListPage


class OrderWorklistPage(WorklistPage):
    searchable = True
    paginated = True
    status_filter: list[tuple] = []
    columns = OrdersListPage.columns

    def __init__(self, presenter, *, title: str, subtitle: str, empty_message: str,
                 parent=None) -> None:
        # La base lee título, subtítulo y mensaje vacío dentro de su `__init__`:
        # se fijan antes, como atributos de instancia, para que cada bandeja
        # muestre los suyos y no los de la clase.
        self.title = title
        self.subtitle = subtitle
        self.empty_message = empty_message
        super().__init__(presenter, parent)
        self.setAccessibleName(title)
        self.setAccessibleDescription(subtitle)

    def _load(self) -> None:
        model = self._presenter.orders(
            query=self._search.query() if self.searchable else "", page=self._page)
        self.set_table(model)
