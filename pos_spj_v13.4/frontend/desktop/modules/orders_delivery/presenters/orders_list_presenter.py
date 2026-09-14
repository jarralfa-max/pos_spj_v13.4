"""OrdersListPresenter (ORD-28) — "Todos los pedidos" worklist data source
PLUS "Nuevo pedido" creation (one presenter per page with multiple methods —
same convention `ExpensesPage`'s own presenter already follows for its list
+ its "Solicitar gasto" dialog).

The list read goes through `OrdersListQueryService`, which is where the
lightweight SQL lives — the same precedent `OrdersDeliveryAnalyticsQueryService`
and `OrdersDeliveryBadgeQueryService` already set. It used to live HERE, in the
presenter, executing against the connection from the presentation layer; the
precedent this docstring cited was about query SERVICES, and this file is not
one. `test_no_sql_in_frontend` caught it the moment that guardrail stopped
scanning deleted folders and started looking at the real UI.

Order creation already went through `CreateCustomerOrderUseCase` and is
unchanged. This presenter now holds no SQL at all.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from backend.application.orders_delivery.authorization import OrdersDeliveryAuthorizationPolicy
from backend.application.orders_delivery.queries.orders_list_query_service import (
    OrdersListQueryService,
)
from backend.application.orders_delivery.use_cases.order_capture_use_cases import (
    CreateCustomerOrderUseCase,
)
from backend.shared.ids import new_uuid


@dataclass(frozen=True, slots=True)
class OrdersTableModel:
    rows: list[list[str]]
    row_ids: list[str]
    total: int


class OrdersListPresenter:
    def __init__(self, connection, *, branch_id: str, actor_user_id: str, page_size: int = 50,
                 authorization: OrdersDeliveryAuthorizationPolicy | None = None) -> None:
        self._conn = connection
        self._branch_id = branch_id
        self._actor_user_id = actor_user_id
        self._page_size = page_size
        self._authorization = authorization

    def create_order(self, dialog_data: dict) -> tuple[bool, str]:
        result = CreateCustomerOrderUseCase(self._authorization).execute(
            self._conn, branch_id=self._branch_id, channel=dialog_data["channel"],
            order_type="STANDARD", fulfillment_type=dialog_data["fulfillment_type"],
            lines=dialog_data["lines"], actor_user_id=self._actor_user_id,
            operation_id=new_uuid(), contact_name=dialog_data.get("contact_name"),
            contact_phone=dialog_data.get("contact_phone"))
        return result.success, result.message

    def orders(self, *, query: str = "", status: str | None = None, page: int = 0) -> OrdersTableModel:
        """La consulta la hace `OrdersListQueryService`; aqui solo se da formato.

        Antes este metodo armaba y ejecutaba el SQL contra la conexion, desde la
        capa de presentacion. Lo senalo `test_no_sql_in_frontend` en cuanto la
        guardia dejo de escanear carpetas borradas y empezo a mirar la UI real.
        """
        pagina = OrdersListQueryService(self._conn).list_for_branch(
            self._branch_id, query=query, status=status,
            page=page, page_size=self._page_size)
        return format_orders_page(pagina)


def format_orders_page(pagina) -> OrdersTableModel:
    """Da formato a una página de pedidos para la rejilla.

    Compartida con las bandejas (`OrderWorklistPresenter`): dos copias del
    formato divergirían en silencio —una columna en otro orden y la tabla
    muestra el dato equivocado bajo el encabezado correcto—.
    """
    filas = [
        [
            fila.order_number or fila.id[:8],
            fila.channel, fila.status, fila.fulfillment_status,
            f"${Decimal(fila.grand_total or '0'):,.2f}",
            fila.contact_name or "—",
            fila.created_at[:16].replace("T", " "),
        ]
        for fila in pagina.rows
    ]
    return OrdersTableModel(
        rows=filas, row_ids=[fila.id for fila in pagina.rows], total=pagina.total)
