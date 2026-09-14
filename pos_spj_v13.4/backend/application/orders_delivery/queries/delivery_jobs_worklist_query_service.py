"""DeliveryJobsWorklistQueryService — lectura paginada de las bandejas de reparto.

Lee `delivery_jobs` directamente y no a través de `DeliveryJobRepository`: ese
repositorio hidrata el agregado completo, con sus intentos, y no pagina ni busca.
Una rejilla necesita ocho columnas. Las ESCRITURAS siguen yendo por los casos de
uso de despacho, reentrega y retorno.

El folio del pedido y el nombre de contacto vienen de `customer_orders` con un
LEFT JOIN: un trabajo cuyo pedido no se encuentre sigue apareciendo, con esos
datos vacíos, en vez de desaparecer de la bandeja.
"""

from __future__ import annotations

from dataclasses import dataclass

from backend.application.orders_delivery.queries.delivery_worklists import (
    DeliveryWorklist,
    delivery_worklist_filter,
)


@dataclass(frozen=True, slots=True)
class DeliveryJobRow:
    """Una fila de la rejilla. Valores tal cual se guardan; el formato es de la vista."""

    id: str
    delivery_number: str
    order_number: str
    contact_name: str
    status: str
    assigned_driver_id: str
    last_failure_reason: str
    updated_at: str


@dataclass(frozen=True, slots=True)
class DeliveryJobListPage:
    rows: list[DeliveryJobRow]
    #: Total que cumple el filtro, no el de la página.
    total: int


#: El motivo mostrado es el del ÚLTIMO intento fallido: un trabajo puede
#: acumular varios, y el que explica su estado actual es el más reciente.
_SELECT = (
    "SELECT j.id, j.delivery_number, o.order_number, o.contact_name, j.status,"
    " j.assigned_driver_id,"
    " (SELECT a.failure_reason FROM delivery_attempts a"
    "   WHERE a.delivery_job_id = j.id AND a.successful = 0"
    "   ORDER BY a.attempted_at DESC LIMIT 1),"
    " j.updated_at"
)
_FROM = " FROM delivery_jobs j LEFT JOIN customer_orders o ON o.id = j.order_id"


class DeliveryJobsWorklistQueryService:
    def __init__(self, db) -> None:
        self.db = db

    def list_worklist(
        self, branch_id: str, worklist: DeliveryWorklist, *, query: str = "",
        page: int = 0, page_size: int = 50,
    ) -> DeliveryJobListPage:
        """Una bandeja de reparto de la sucursal.

        `branch_id` siempre entra en el WHERE: sin él la bandeja mostraría las
        entregas de todas las sucursales y parecería funcionar. El filtro de estados
        sale de `delivery_worklists`, el mismo que cuenta el badge.
        """
        filtro = delivery_worklist_filter(worklist)
        where = ["j.branch_id=?", f"({filtro.sql})"]
        valores: list = [branch_id, *filtro.params]
        if query:
            where.append(
                "(j.delivery_number LIKE ? OR o.order_number LIKE ?"
                " OR o.contact_name LIKE ? OR o.contact_phone LIKE ?)")
            like = f"%{query}%"
            valores += [like, like, like, like]
        where_sql = " AND ".join(where)

        total = self.db.execute(
            f"SELECT COUNT(*){_FROM} WHERE {where_sql}", valores).fetchone()[0]
        filas = self.db.execute(
            f"{_SELECT}{_FROM} WHERE {where_sql}"
            " ORDER BY j.updated_at DESC LIMIT ? OFFSET ?",
            [*valores, page_size, page * page_size]).fetchall()

        return DeliveryJobListPage(
            rows=[DeliveryJobRow(*[("" if valor is None else str(valor)) for valor in fila])
                  for fila in filas],
            total=total)
