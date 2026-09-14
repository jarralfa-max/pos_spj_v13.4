"""OrderWorklistPresenter (PASS 6) — datos de una bandeja de pedidos.

No arma SQL: pide la página a `OrdersListQueryService.list_worklist`, que filtra
con la MISMA definición que cuenta el badge del sidebar (`order_worklists`), y le
da formato con la misma función que "Todos los pedidos".
"""

from __future__ import annotations

from backend.application.orders_delivery.queries.order_worklists import OrderWorklist
from backend.application.orders_delivery.queries.orders_list_query_service import (
    OrdersListQueryService,
)
from frontend.desktop.modules.orders_delivery.presenters.orders_list_presenter import (
    OrdersTableModel,
    format_orders_page,
)


class OrderWorklistPresenter:
    def __init__(self, connection, *, branch_id: str, worklist: OrderWorklist,
                 page_size: int = 50) -> None:
        self._conn = connection
        self._branch_id = branch_id
        self._worklist = worklist
        self._page_size = page_size

    @property
    def worklist(self) -> OrderWorklist:
        return self._worklist

    def orders(self, *, query: str = "", page: int = 0) -> OrdersTableModel:
        pagina = OrdersListQueryService(self._conn).list_worklist(
            self._branch_id, self._worklist, query=query, page=page,
            page_size=self._page_size)
        return format_orders_page(pagina)
