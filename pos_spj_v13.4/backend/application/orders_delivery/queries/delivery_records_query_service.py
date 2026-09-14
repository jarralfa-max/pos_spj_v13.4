"""DeliveryRecordsQueryService — los registros de reparto que no son un estado del
trabajo: reentregas, cobros en ruta, liquidaciones y rutas.

POR QUÉ NO SON BANDEJAS
-----------------------
Las bandejas (`delivery_worklists`, `order_worklists`) filtran un conjunto fijo de
estados. Estas cuatro pantallas son REGISTROS: enseñan todo lo de la sucursal, con
filtro por estado, y ponen primero lo que pide atención (una reentrega por decidir,
un cobro sin cerrar, una liquidación sin cerrar, una ruta sin terminar).

DE QUÉ SUCURSAL ES CADA COSA
----------------------------
`redelivery_requests` y `driver_cash_collections` no tienen `branch_id`: la sucursal
es la de su trabajo de reparto, y se filtra por `delivery_jobs.branch_id` con un JOIN.
Leerlos sin ese JOIN enseñaría los de todas las sucursales. `driver_settlements` y
`delivery_routes` sí la tienen.

Las lecturas van directo a las tablas y no por los repositorios, que hidratan el
agregado completo y no paginan. Las escrituras siguen yendo por los casos de uso.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from enum import Enum

from backend.domain.orders_delivery.enums import (
    CollectionStatus,
    RedeliveryStatus,
    RouteStatus,
    SettlementStatus,
)


class DeliveryRecord(str, Enum):
    REDELIVERIES = "redeliveries"
    CASH_COLLECTIONS = "cash_collections"
    SETTLEMENTS = "settlements"
    ROUTES = "routes"


#: El enum de estados de cada registro: valida el filtro y da las opciones del combo.
STATUS_ENUM: dict[DeliveryRecord, type[Enum]] = {
    DeliveryRecord.REDELIVERIES: RedeliveryStatus,
    DeliveryRecord.CASH_COLLECTIONS: CollectionStatus,
    DeliveryRecord.SETTLEMENTS: SettlementStatus,
    DeliveryRecord.ROUTES: RouteStatus,
}

#: Estados que piden que alguien haga algo. Van arriba de la lista.
_ATENCION: dict[DeliveryRecord, tuple[Enum, ...]] = {
    DeliveryRecord.REDELIVERIES: (RedeliveryStatus.PENDING,),
    DeliveryRecord.CASH_COLLECTIONS: (
        CollectionStatus.EXPECTED, CollectionStatus.PARTIALLY_COLLECTED,
        CollectionStatus.FAILED, CollectionStatus.DISPUTED),
    # Toda liquidación sin cerrar sigue abierta para alguien.
    DeliveryRecord.SETTLEMENTS: tuple(s for s in SettlementStatus if s is not SettlementStatus.CLOSED),
    DeliveryRecord.ROUTES: (
        RouteStatus.DRAFT, RouteStatus.PLANNED, RouteStatus.ASSIGNED, RouteStatus.ACTIVE),
}


@dataclass(frozen=True, slots=True)
class _Consulta:
    columnas: tuple[tuple[str, str], ...]
    desde: str
    sucursal: str
    estado: str
    orden: str
    buscar_en: tuple[str, ...] = ()


_CONSULTAS: dict[DeliveryRecord, _Consulta] = {
    DeliveryRecord.REDELIVERIES: _Consulta(
        columnas=(
            ("id", "r.id"), ("created_at", "r.created_at"),
            ("delivery_number", "j.delivery_number"), ("order_number", "o.order_number"),
            ("contact_name", "o.contact_name"), ("reason", "r.reason"),
            ("additional_fee", "r.additional_fee"), ("status", "r.status"),
            ("new_delivery_job_id", "r.new_delivery_job_id"),
        ),
        desde=("redelivery_requests r"
               " JOIN delivery_jobs j ON j.id = r.original_delivery_job_id"
               " LEFT JOIN customer_orders o ON o.id = j.order_id"),
        sucursal="j.branch_id", estado="r.status", orden="r.updated_at DESC, r.id DESC",
        buscar_en=("j.delivery_number", "o.order_number", "o.contact_name", "r.reason"),
    ),
    DeliveryRecord.CASH_COLLECTIONS: _Consulta(
        columnas=(
            ("id", "c.id"), ("delivery_number", "j.delivery_number"),
            ("order_number", "o.order_number"), ("contact_name", "o.contact_name"),
            ("driver_id", "c.driver_id"), ("payment_method", "c.payment_method"),
            ("expected_amount", "c.expected_amount"), ("collected_amount", "c.collected_amount"),
            ("status", "c.status"), ("collected_at", "c.collected_at"),
        ),
        desde=("driver_cash_collections c"
               " JOIN delivery_jobs j ON j.id = c.delivery_job_id"
               " LEFT JOIN customer_orders o ON o.id = j.order_id"),
        sucursal="j.branch_id", estado="c.status", orden="c.updated_at DESC, c.id DESC",
        buscar_en=("j.delivery_number", "o.order_number", "o.contact_name", "c.reference"),
    ),
    DeliveryRecord.SETTLEMENTS: _Consulta(
        columnas=(
            ("id", "s.id"), ("created_at", "s.created_at"), ("driver_id", "s.driver_id"),
            ("collection_ids_json", "s.collection_ids_json"),
            ("expected_total", "s.expected_total"), ("collected_total", "s.collected_total"),
            ("status", "s.status"),
        ),
        desde="driver_settlements s",
        sucursal="s.branch_id", estado="s.status", orden="s.updated_at DESC, s.id DESC",
    ),
    DeliveryRecord.ROUTES: _Consulta(
        columnas=(
            ("id", "r.id"), ("status", "r.status"), ("assigned_driver_id", "r.assigned_driver_id"),
            ("stop_count", "(SELECT COUNT(*) FROM delivery_route_stops p WHERE p.route_id = r.id)"),
            ("created_at", "r.created_at"), ("updated_at", "r.updated_at"),
        ),
        desde="delivery_routes r",
        sucursal="r.branch_id", estado="r.status", orden="r.updated_at DESC, r.id DESC",
    ),
}

#: Registros con búsqueda de texto. Liquidaciones y rutas no tienen un texto que
#: buscar: sin nombre de repartidor (ver el presenter), sólo quedarían ids.
SEARCHABLE_RECORDS = frozenset(r for r, c in _CONSULTAS.items() if c.buscar_en)


@dataclass(frozen=True, slots=True)
class DeliveryRecordPage:
    #: Una fila por registro, con las claves de `_CONSULTAS`. Valores tal cual se guardan.
    rows: list[dict]
    #: Total que cumple el filtro, no el de la página.
    total: int


class DeliveryRecordsQueryService:
    def __init__(self, db) -> None:
        self.db = db

    def list_records(
        self, branch_id: str, record: DeliveryRecord, *, status: str | None = None,
        query: str = "", page: int = 0, page_size: int = 50,
    ) -> DeliveryRecordPage:
        """Un registro de la sucursal, lo que pide atención primero.

        `status` tiene que ser un valor del enum del registro: un estado inventado
        devolvería una lista vacía que parecería "no hay nada" (`ValueError`).
        """
        record = DeliveryRecord(record)
        consulta = _CONSULTAS[record]

        where = [f"{consulta.sucursal}=?"]
        valores: list = [branch_id]
        if status:
            where.append(f"{consulta.estado}=?")
            valores.append(STATUS_ENUM[record](status).value)
        if query:
            if not consulta.buscar_en:
                raise ValueError(f"El registro {record.value} no admite búsqueda")
            where.append("(" + " OR ".join(f"{c} LIKE ?" for c in consulta.buscar_en) + ")")
            valores += [f"%{query}%"] * len(consulta.buscar_en)
        where_sql = " AND ".join(where)

        total = self.db.execute(
            f"SELECT COUNT(*) FROM {consulta.desde} WHERE {where_sql}", valores).fetchone()[0]

        atencion = _ATENCION[record]
        marcas = ",".join("?" for _ in atencion)
        select = ", ".join(expr for _, expr in consulta.columnas)
        filas = self.db.execute(
            f"SELECT {select} FROM {consulta.desde} WHERE {where_sql}"
            f" ORDER BY CASE WHEN {consulta.estado} IN ({marcas}) THEN 0 ELSE 1 END,"
            f" {consulta.orden} LIMIT ? OFFSET ?",
            [*valores, *(estado.value for estado in atencion), page_size, page * page_size],
        ).fetchall()

        nombres = [nombre for nombre, _ in consulta.columnas]
        rows = [dict(zip(nombres, fila)) for fila in filas]
        if record is DeliveryRecord.SETTLEMENTS:
            for fila in rows:
                fila["collection_count"] = len(json.loads(fila.pop("collection_ids_json") or "[]"))
        return DeliveryRecordPage(rows=rows, total=total)
