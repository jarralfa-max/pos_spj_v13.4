"""OrdersListQueryService — la lectura paginada de "Todos los pedidos".

POR QUÉ EXISTE ESTE ARCHIVO
---------------------------
Esta consulta vivía dentro de `OrdersListPresenter`, en `frontend/`, armando y
ejecutando SQL contra la conexión desde la capa de presentación. El propio
docstring del presentador invocaba el precedente correcto —"los servicios de
consulta hacen su propio SQL ligero", como ya hacen
`OrdersDeliveryAnalyticsQueryService` y `OrdersDeliveryBadgeQueryService`— pero
el SQL se había quedado en el presentador en vez de en un servicio de consulta.
Eso es lo que CLAUDE.md prohíbe en sus reglas 7 y 13: la UI no ejecuta SQL.

No se descubrió leyéndolo: la guardia `test_no_sql_in_frontend` lo señaló en
cuanto dejó de escanear carpetas borradas. Llevaba invisible desde que se
escribió.

Se lee `customer_orders` directamente y no a través de
`CustomerOrderRepository`: ese repositorio hidrata el agregado completo y no
tiene `list_for_branch` —nada lo necesitaba— y una rejilla paginada no necesita
el agregado, sólo ocho columnas. La ESCRITURA de pedidos sigue yendo por
`CreateCustomerOrderUseCase`, como ya hacía.
"""

from __future__ import annotations

from dataclasses import dataclass

from backend.application.orders_delivery.queries.order_worklists import (
    OrderWorklist,
    worklist_filter,
)


@dataclass(frozen=True, slots=True)
class OrderListRow:
    """Una fila de la rejilla. Los valores llegan tal cual están guardados: dar
    formato (moneda, fecha, guion para lo vacío) es trabajo de la vista, no de
    la consulta."""

    id: str
    order_number: str
    channel: str
    status: str
    fulfillment_status: str
    grand_total: str
    contact_name: str
    created_at: str


@dataclass(frozen=True, slots=True)
class OrderListPage:
    rows: list[OrderListRow]
    #: Total que cumple el filtro, NO el de la página: la barra de paginación
    #: necesita saber cuántas hay en total para calcular cuántas páginas hay.
    total: int


#: Las columnas que la rejilla muestra, en su orden. Nombrarlas una sola vez
#: evita que el SELECT y el desempaquetado se desincronicen en silencio.
_COLUMNS = ("id", "order_number", "channel", "status", "fulfillment_status",
            "grand_total", "contact_name", "created_at")


class OrdersListQueryService:
    def __init__(self, db) -> None:
        self.db = db

    def list_for_branch(
        self, branch_id: str, *, query: str = "", status: str | None = None,
        page: int = 0, page_size: int = 50,
    ) -> OrderListPage:
        """Pedidos de la sucursal, filtrados y paginados.

        `branch_id` no es opcional y siempre entra en el WHERE: una rejilla de
        pedidos sin filtro de sucursal mostraría los de todas, que es una fuga
        de datos entre sucursales, no un fallo visible.
        """
        condiciones: list[str] = []
        params: list = []
        if status:
            condiciones.append("o.status=?")
            params.append(status)
        return self._pagina(branch_id, condiciones, params,
                            query=query, page=page, page_size=page_size)

    def list_worklist(
        self, branch_id: str, worklist: OrderWorklist, *, query: str = "",
        page: int = 0, page_size: int = 50,
    ) -> OrderListPage:
        """Una bandeja de trabajo del sidebar.

        El filtro sale de `order_worklists`, el MISMO que cuenta su badge: si
        divergieran, el contador y la lista discreparían sin ningún error
        visible. Sucursal, búsqueda y paginación son las de siempre.
        """
        filtro = worklist_filter(worklist)
        return self._pagina(branch_id, [f"({filtro.sql})"], list(filtro.params),
                            query=query, page=page, page_size=page_size)

    def _pagina(self, branch_id: str, condiciones: list[str], params: list, *,
                query: str, page: int, page_size: int) -> OrderListPage:
        where = ["o.branch_id=?", *condiciones]
        valores: list = [branch_id, *params]
        if query:
            where.append(
                "(o.order_number LIKE ? OR o.contact_name LIKE ? OR o.contact_phone LIKE ?)")
            like = f"%{query}%"
            valores += [like, like, like]
        where_sql = " AND ".join(where)

        # El WHERE se interpola porque se arma con literales de este módulo y de
        # `order_worklists`; todo VALOR va como parámetro enlazado.
        total = self.db.execute(
            f"SELECT COUNT(*) FROM customer_orders o WHERE {where_sql}",
            valores).fetchone()[0]

        filas = self.db.execute(
            f"SELECT {', '.join('o.' + columna for columna in _COLUMNS)}"
            f" FROM customer_orders o WHERE {where_sql}"
            f" ORDER BY o.created_at DESC LIMIT ? OFFSET ?",
            [*valores, page_size, page * page_size]).fetchall()

        return OrderListPage(rows=[_a_fila(fila) for fila in filas], total=total)

def _a_fila(fila) -> OrderListRow:
    """Convierte la fila cruda en el DTO.

    `None` se vuelve cadena vacia en vez de propagarse: la vista decide como se
    muestra lo que falta (un guion), y dejar `None` obligaria a cada consumidor
    a acordarse de comprobarlo.
    """
    return OrderListRow(*[("" if valor is None else str(valor)) for valor in fila])
