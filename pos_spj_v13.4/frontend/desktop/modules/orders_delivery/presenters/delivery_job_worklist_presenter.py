"""DeliveryJobWorklistPresenter (PASS 6) — datos de una bandeja de reparto.

No arma SQL: pide la página a `DeliveryJobsWorklistQueryService`, que filtra con
la MISMA definición que cuenta el badge (`delivery_worklists`).
"""

from __future__ import annotations

from backend.application.orders_delivery.queries.delivery_jobs_worklist_query_service import (
    DeliveryJobsWorklistQueryService,
)
from backend.application.orders_delivery.queries.delivery_worklists import DeliveryWorklist
from frontend.desktop.modules.orders_delivery.presenters.orders_list_presenter import (
    OrdersTableModel,
)


class DeliveryJobWorklistPresenter:
    def __init__(self, connection, *, branch_id: str, worklist: DeliveryWorklist,
                 page_size: int = 50) -> None:
        self._conn = connection
        self._branch_id = branch_id
        self._worklist = worklist
        self._page_size = page_size

    @property
    def worklist(self) -> DeliveryWorklist:
        return self._worklist

    def jobs(self, *, query: str = "", page: int = 0) -> OrdersTableModel:
        pagina = DeliveryJobsWorklistQueryService(self._conn).list_worklist(
            self._branch_id, self._worklist, query=query, page=page,
            page_size=self._page_size)
        filas = [
            [
                fila.delivery_number or fila.id[:8],
                fila.order_number or "—",
                fila.contact_name or "—",
                fila.status,
                # Sin nombre, a propósito: `driver_id` sólo se valida como UUIDv7 y
                # no se cruza con ninguna tabla de personas, así que no hay de dónde
                # leerlo. Se muestra el id corto en vez de inventar ese cruce.
                fila.assigned_driver_id[:8] if fila.assigned_driver_id else "Sin asignar",
                fila.last_failure_reason or "—",
                fila.updated_at[:16].replace("T", " "),
            ]
            for fila in pagina.rows
        ]
        return OrdersTableModel(
            rows=filas, row_ids=[fila.id for fila in pagina.rows], total=pagina.total)
