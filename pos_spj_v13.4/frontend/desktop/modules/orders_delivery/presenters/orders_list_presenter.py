"""OrdersListPresenter (ORD-28) — "Todos los pedidos" worklist data source
PLUS "Nuevo pedido" creation (one presenter per page with multiple methods —
same convention `ExpensesPage`'s own presenter already follows for its list
+ its "Solicitar gasto" dialog). The list query is lightweight, read-only
SQL directly against `customer_orders` (never through the full
`CustomerOrderRepository`/domain hydration, which has no `list_for_branch`
— nothing needed it until this page) — same "query services do their own
lightweight SQL" precedent already set by `OrdersDeliveryAnalyticsQueryService`/
`OrdersDeliveryBadgeQueryService`. Order CREATION, unlike the list read,
goes through the real `CreateCustomerOrderUseCase` — this presenter never
writes SQL itself.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from backend.application.orders_delivery.authorization import OrdersDeliveryAuthorizationPolicy
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
        where = ["branch_id=?"]
        params: list = [self._branch_id]
        if status:
            where.append("status=?")
            params.append(status)
        if query:
            where.append("(order_number LIKE ? OR contact_name LIKE ? OR contact_phone LIKE ?)")
            like = f"%{query}%"
            params += [like, like, like]
        where_sql = " AND ".join(where)

        total = self._conn.execute(
            f"SELECT COUNT(*) FROM customer_orders WHERE {where_sql}", params).fetchone()[0]
        rows_raw = self._conn.execute(
            f"SELECT id, order_number, channel, status, fulfillment_status, grand_total,"
            f" contact_name, created_at FROM customer_orders WHERE {where_sql}"
            f" ORDER BY created_at DESC LIMIT ? OFFSET ?",
            [*params, self._page_size, page * self._page_size]).fetchall()

        rows = [
            [
                order_number or order_id[:8],
                channel, status_value, fulfillment_status,
                f"${Decimal(str(grand_total or '0')):,.2f}",
                contact_name or "—",
                (created_at or "")[:16].replace("T", " "),
            ]
            for order_id, order_number, channel, status_value, fulfillment_status,
                grand_total, contact_name, created_at in rows_raw
        ]
        row_ids = [row[0] for row in rows_raw]
        return OrdersTableModel(rows=rows, row_ids=row_ids, total=total)
