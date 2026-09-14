"""DeliveryRecordsQueryService — los registros de reparto que no son un estado del
trabajo: reentregas, cobros en ruta, liquidaciones, rutas, seguimiento, incidencias
y alertas.

POR QUÉ NO SON BANDEJAS
-----------------------
Las bandejas (`delivery_worklists`, `order_worklists`) filtran un conjunto fijo de
estados. Estas pantallas son REGISTROS: enseñan todo lo de la sucursal, con filtro
por estado, y ponen primero lo que pide atención (una reentrega por decidir, un
cobro sin cerrar, una ruta sin terminar, una entrega en curso, una alerta sin leer).

DE QUÉ SUCURSAL ES CADA COSA
----------------------------
`redelivery_requests`, `driver_cash_collections` y `delivery_attempts` no tienen
`branch_id`: la sucursal es la de su trabajo de reparto, y se filtra por
`delivery_jobs.branch_id` con un JOIN. Leerlos sin ese JOIN enseñaría los de todas
las sucursales. `driver_settlements`, `delivery_routes` y `customer_orders` sí la
tienen; `notification_inbox` la guarda como `sucursal_id`.

QUÉ ES CADA REGISTRO NUEVO
--------------------------
- Auditoría: `audit_logs` del módulo DELIVERY en la sucursal. La escriben los
  casos de uso en la misma transacción que su cambio (ver `audit.py`).
- Seguimiento: un renglón por PEDIDO con reparto, con su trabajo MÁS RECIENTE.
  Aprobar una reentrega crea un trabajo nuevo y el viejo se queda en
  `REDELIVERY_PENDING` para siempre; enseñar ese estado diría que el pedido sigue
  esperando reentrega cuando ya va en camino. Los pedidos sin trabajo (mostrador,
  recoger) no aparecen: no hay entrega que seguir.
- Incidencias: cada intento de entrega FALLIDO, con su motivo del catálogo
  `FailureReason`. No existe otra tabla de incidencias ni nadie que la escriba;
  el intento fallido es lo que de verdad se registra durante la entrega.
- Alertas: la bandeja `notification_inbox` es POR PERSONA — el notificador escribe
  un renglón por cada admin/gerente, y "leída" es de quien la leyó. Por eso este
  registro exige `recipient_user_id`: sin él, una alerta aparecería una vez por
  destinatario y "sin leer" no significaría nada.

Las lecturas van directo a las tablas y no por los repositorios, que hidratan el
agregado completo y no paginan. Las escrituras siguen yendo por los casos de uso.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from enum import Enum

from backend.application.orders_delivery.audit import ALL_AUDIT_ACTIONS, AUDIT_MODULE
from backend.domain.orders_delivery.enums import (
    CollectionStatus,
    DeliveryStatus,
    FailureReason,
    RedeliveryStatus,
    RouteStatus,
    SettlementStatus,
)
from backend.domain.orders_delivery.policies.notification_policy import DELIVERY_ALERT_TYPES


class DeliveryRecord(str, Enum):
    REDELIVERIES = "redeliveries"
    CASH_COLLECTIONS = "cash_collections"
    SETTLEMENTS = "settlements"
    ROUTES = "routes"
    TRACKING = "tracking"
    INCIDENTS = "incidents"
    ALERTS = "alerts"
    AUDIT = "audit"


class AlertStatus(str, Enum):
    """`notification_inbox.leido` es 0/1; el filtro necesita un vocabulario."""

    UNREAD = "UNREAD"
    READ = "READ"


#: El filtro de Auditoría es la acción; su vocabulario lo fija `audit.py`.
AuditAction = Enum("AuditAction", [(accion, accion) for accion in sorted(ALL_AUDIT_ACTIONS)],
                   type=str)


#: El enum de estados de cada registro: valida el filtro y da las opciones del combo.
#: En incidencias "estado" es el motivo de la falla.
STATUS_ENUM: dict[DeliveryRecord, type[Enum]] = {
    DeliveryRecord.REDELIVERIES: RedeliveryStatus,
    DeliveryRecord.CASH_COLLECTIONS: CollectionStatus,
    DeliveryRecord.SETTLEMENTS: SettlementStatus,
    DeliveryRecord.ROUTES: RouteStatus,
    DeliveryRecord.TRACKING: DeliveryStatus,
    DeliveryRecord.INCIDENTS: FailureReason,
    DeliveryRecord.ALERTS: AlertStatus,
    DeliveryRecord.AUDIT: AuditAction,
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
    # Lo que todavía no termina: sigue en manos de alguien.
    DeliveryRecord.TRACKING: tuple(
        s for s in DeliveryStatus
        if s not in (DeliveryStatus.DELIVERED, DeliveryStatus.RETURNED_TO_BRANCH,
                     DeliveryStatus.CANCELLED, DeliveryStatus.CLOSED)),
    # Una incidencia no se "atiende" en esta tabla: van por fecha, la más reciente arriba.
    DeliveryRecord.INCIDENTS: (),
    DeliveryRecord.ALERTS: (AlertStatus.UNREAD,),
    # Un rastro no se atiende: va por fecha, lo más reciente arriba.
    DeliveryRecord.AUDIT: (),
}


@dataclass(frozen=True, slots=True)
class _Consulta:
    columnas: tuple[tuple[str, str], ...]
    desde: str
    sucursal: str
    estado: str
    orden: str
    buscar_en: tuple[str, ...] = ()
    #: Condición fija del registro, con sus parámetros.
    extra: str = ""
    extra_params: tuple = ()
    #: Columna del destinatario, para los registros que son por persona.
    destinatario: str = ""


_TIPOS_ALERTA = tuple(sorted(DELIVERY_ALERT_TYPES))

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
    DeliveryRecord.TRACKING: _Consulta(
        columnas=(
            ("id", "o.id"), ("order_number", "o.order_number"),
            ("contact_name", "o.contact_name"), ("contact_phone", "o.contact_phone"),
            ("order_status", "o.status"), ("job_status", "j.status"),
            ("assigned_driver_id", "j.assigned_driver_id"), ("dispatched_at", "j.dispatched_at"),
            ("estimated_arrival_at", "j.estimated_arrival_at"),
            ("delivered_at", "j.delivered_at"), ("failed_at", "j.failed_at"),
            ("attempts", "(SELECT COUNT(*) FROM delivery_attempts a WHERE a.delivery_job_id = j.id)"),
        ),
        # El trabajo más reciente del pedido; UUIDv7 desempata dentro del mismo segundo.
        desde=("customer_orders o JOIN delivery_jobs j ON j.id = ("
               "SELECT j2.id FROM delivery_jobs j2 WHERE j2.order_id = o.id"
               " ORDER BY j2.created_at DESC, j2.id DESC LIMIT 1)"),
        sucursal="o.branch_id", estado="j.status", orden="j.updated_at DESC, j.id DESC",
        buscar_en=("o.order_number", "o.contact_name", "o.contact_phone", "j.delivery_number"),
    ),
    DeliveryRecord.INCIDENTS: _Consulta(
        columnas=(
            ("id", "a.id"), ("attempted_at", "a.attempted_at"),
            ("delivery_number", "j.delivery_number"), ("order_number", "o.order_number"),
            ("contact_name", "o.contact_name"), ("driver_id", "j.assigned_driver_id"),
            ("failure_reason", "a.failure_reason"), ("notes", "a.evidence_notes"),
            ("job_status", "j.status"),
        ),
        desde=("delivery_attempts a"
               " JOIN delivery_jobs j ON j.id = a.delivery_job_id"
               " LEFT JOIN customer_orders o ON o.id = j.order_id"),
        sucursal="j.branch_id", estado="a.failure_reason",
        orden="a.attempted_at DESC, a.id DESC",
        buscar_en=("j.delivery_number", "o.order_number", "o.contact_name", "a.evidence_notes"),
        extra="a.successful = 0",
    ),
    DeliveryRecord.ALERTS: _Consulta(
        columnas=(
            ("id", "n.id"), ("created_at", "n.created_at"), ("title", "n.titulo"),
            ("body", "n.cuerpo"),
            ("status", "CASE WHEN n.leido = 1 THEN 'READ' ELSE 'UNREAD' END"),
            ("read_at", "n.leido_at"),
        ),
        desde="notification_inbox n",
        sucursal="n.sucursal_id",
        estado="(CASE WHEN n.leido = 1 THEN 'READ' ELSE 'UNREAD' END)",
        orden="n.created_at DESC, n.id DESC",
        buscar_en=("n.titulo", "n.cuerpo"),
        extra=f"n.tipo IN ({','.join('?' for _ in _TIPOS_ALERTA)})",
        extra_params=_TIPOS_ALERTA,
        destinatario="n.empleado_id",
    ),
    DeliveryRecord.AUDIT: _Consulta(
        columnas=(
            ("id", "a.id"), ("occurred_at", "a.fecha"), ("actor", "a.usuario"),
            ("action", "a.accion"), ("entity", "a.entidad"),
            ("entity_id", "a.entidad_id"), ("after", "a.valor_despues"),
        ),
        desde="audit_logs a",
        sucursal="a.sucursal_id", estado="a.accion", orden="a.fecha DESC, a.id DESC",
        buscar_en=("a.entidad_id", "a.usuario", "a.valor_despues"),
        # `audit_logs` es transversal: sólo lo de este módulo.
        extra="a.modulo = ?", extra_params=(AUDIT_MODULE,),
    ),
}

#: Registros con búsqueda de texto. Liquidaciones y rutas no tienen un texto que
#: buscar: sin nombre de repartidor (ver el presenter), sólo quedarían ids.
SEARCHABLE_RECORDS = frozenset(r for r, c in _CONSULTAS.items() if c.buscar_en)

#: Registros que son por persona: exigen `recipient_user_id`.
PER_RECIPIENT_RECORDS = frozenset(r for r, c in _CONSULTAS.items() if c.destinatario)


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
        recipient_user_id: str | None = None,
    ) -> DeliveryRecordPage:
        """Un registro de la sucursal, lo que pide atención primero.

        `status` tiene que ser un valor del enum del registro: un estado inventado
        devolvería una lista vacía que parecería "no hay nada" (`ValueError`). Por
        la misma razón, un registro por persona sin `recipient_user_id` se rechaza.
        """
        record = DeliveryRecord(record)
        consulta = _CONSULTAS[record]

        where = [f"{consulta.sucursal}=?"]
        valores: list = [branch_id]
        if consulta.extra:
            where.append(f"({consulta.extra})")
            valores += list(consulta.extra_params)
        if consulta.destinatario:
            if not recipient_user_id:
                raise ValueError(
                    f"El registro {record.value} es por persona: falta el usuario de la sesión")
            where.append(f"{consulta.destinatario}=?")
            valores.append(recipient_user_id)
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
        orden_valores: list = []
        orden = consulta.orden
        if atencion:
            marcas = ",".join("?" for _ in atencion)
            orden = f"CASE WHEN {consulta.estado} IN ({marcas}) THEN 0 ELSE 1 END, {orden}"
            orden_valores = [estado.value for estado in atencion]
        select = ", ".join(expr for _, expr in consulta.columnas)
        filas = self.db.execute(
            f"SELECT {select} FROM {consulta.desde} WHERE {where_sql}"
            f" ORDER BY {orden} LIMIT ? OFFSET ?",
            [*valores, *orden_valores, page_size, page * page_size],
        ).fetchall()

        nombres = [nombre for nombre, _ in consulta.columnas]
        rows = [dict(zip(nombres, fila)) for fila in filas]
        if record is DeliveryRecord.SETTLEMENTS:
            for fila in rows:
                fila["collection_count"] = len(json.loads(fila.pop("collection_ids_json") or "[]"))
        return DeliveryRecordPage(rows=rows, total=total)
