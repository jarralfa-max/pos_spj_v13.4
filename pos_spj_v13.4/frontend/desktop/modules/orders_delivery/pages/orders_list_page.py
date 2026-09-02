"""OrdersListPage (ORD-28) — "Todos los pedidos": a real `WorklistPage`
(search + status filter + table + pagination), not a placeholder. Also
hosts the "Nuevo pedido" header action (mirrors `ExpensesPage`'s exact
convention: the dialog is opened from the list page's own header, not a
separate standalone page)."""

from __future__ import annotations

from frontend.desktop.components import create_primary_button
from frontend.desktop.components.tables import ColumnSpec
from frontend.desktop.components.worklist_page import WorklistPage
from frontend.desktop.modules.orders_delivery.dialogs.new_order_dialog import NewOrderDialog

_STATUS_OPTIONS = [
    ("DRAFT", "Borrador"),
    ("PENDING_CONFIRMATION", "Pendiente de confirmación"),
    ("CONFIRMED", "Confirmado"),
    ("IN_FULFILLMENT", "En preparación/entrega"),
    ("COMPLETED", "Completado"),
    ("CANCELLED", "Cancelado"),
    ("CLOSED", "Cerrado"),
    ("REVERSED", "Reversado"),
]


class OrdersListPage(WorklistPage):
    title = "Todos los pedidos"
    subtitle = "Listado completo de pedidos de la sucursal."
    empty_message = "No hay pedidos que coincidan con el filtro."
    searchable = True
    paginated = True
    status_filter = _STATUS_OPTIONS
    columns = [
        ColumnSpec("Folio"),
        ColumnSpec("Canal"),
        ColumnSpec("Estado", "status"),
        ColumnSpec("Cumplimiento", "status"),
        ColumnSpec("Total", "numeric"),
        ColumnSpec("Cliente"),
        ColumnSpec("Creado", "date"),
    ]

    def __init__(self, presenter, parent=None) -> None:
        super().__init__(presenter, parent)
        self.setAccessibleName("Todos los pedidos")
        self.setAccessibleDescription("Listado completo de pedidos de la sucursal, con "
                                      "búsqueda, filtro por estado y creación de pedidos.")

    def _build_actions(self) -> None:
        new_order_btn = create_primary_button(self, "Nuevo pedido")
        new_order_btn.clicked.connect(self._new_order)
        self.header.add_action(new_order_btn)

    def _new_order(self) -> None:
        dialog = NewOrderDialog(self)
        if dialog.exec_():
            self.notify(*self._presenter.create_order(dialog.data()))

    def _load(self) -> None:
        model = self._presenter.orders(
            query=self._search.query() if self.searchable else "",
            status=self._status_id(), page=self._page)
        self.set_table(model)
