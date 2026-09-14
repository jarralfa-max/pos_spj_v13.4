"""Bandejas de trabajo de Pedidos: UNA definición, la usan la lista y su badge.

POR QUÉ EXISTE
--------------
Seis rutas del sidebar de Pedidos eran placeholder, pero sus contadores (badges)
ya existían en `OrdersDeliveryBadgeQueryService`. Construir cada página con su
propio SQL habría dejado dos definiciones de la misma bandeja: el badge diría 3
y la lista enseñaría 5, sin ningún error visible. La definición vive aquí; el
servicio de badges y el de listas la importan.

TRES BADGES ESTABAN MAL, Y SE VIO AL DERIVARLOS DEL DOMINIO
------------------------------------------------------------
Cada filtro sale de lo que el dominio escribe de verdad —comprobado conduciendo
`CustomerOrder` y persistiéndolo con su repositorio—, no de lo que el nombre
sugiere:

- Preparación contaba `fulfillment_status IN (PENDING, PREPARING)`. Pero
  `mark_reserved()` deja `RESERVED` y `assign_preparation()` EXIGE `RESERVED`:
  los pedidos que esperan ser preparados no aparecían, y los `PENDING` —que el
  dominio prohíbe preparar— sí.
- Ajustes de peso contaba `customer_approval_status='PENDING'`. Pero
  `propose_substitution()` pone esa MISMA aprobación pendiente: las
  sustituciones salían como ajustes de peso. Sólo la sustitución rellena
  `substitute_product_id`, y ése es el discriminador.
- Programados contaba `status='CONFIRMED' AND order_type='SCHEDULED'`. Pero
  `schedule()` pone `schedule_status` y no toca ni `status` ni `order_type`: los
  ya activados contaban como pendientes y los programados con otro tipo de
  pedido no contaban.

PENDIENTES DE CONFIRMACIÓN
--------------------------
Nada en el repositorio escribe `OrderStatus.PENDING_CONFIRMATION`: la política
admite la transición, pero ningún método ni caso de uso la ejecuta, y
`confirm()` pasa de `DRAFT` a `CONFIRMED` directamente. Lo que el tooltip
describe —"pedidos capturados a la espera de confirmación"— es `DRAFT` (más
`PENDING_CONFIRMATION` si algún día se usa). Se excluyen los programados que aún
esperan activación: todavía no están para confirmar, y tienen su bandeja.

LO QUE NO ESTÁ AQUÍ, A PROPÓSITO
--------------------------------
"Entregas activas" y "Entregas fallidas" no son bandejas de pedido. El único
escritor de `fulfillment_status=FAILED` es la reserva de inventario fallida
(`mark_reservation_failed`), y un intento de entrega fallido no toca el pedido:
queda `DISPATCHED`. Su fuente es `delivery_jobs.status`, y se definen en
`delivery_worklists.py`.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from backend.domain.orders_delivery.enums import (
    CustomerApprovalStatus,
    FulfillmentStatus,
    OrderLineStatus,
    OrderStatus,
    ScheduleStatus,
)
from backend.domain.orders_delivery.policies.pickup_policy import PickupPolicy


class OrderWorklist(str, Enum):
    """Los valores coinciden con las claves de badge del sidebar."""

    SCHEDULED_PENDING_ACTIVATION = "scheduled_pending_activation"
    PENDING_CONFIRMATION = "pending_confirmation"
    PREPARATION_QUEUE = "preparation_queue"
    WEIGHT_ADJUSTMENTS_PENDING = "weight_adjustments_pending"
    READY_FOR_PICKUP = "ready_for_pickup"
    READY_FOR_DISPATCH = "ready_for_dispatch"


@dataclass(frozen=True, slots=True)
class WorklistFilter:
    """Condición sobre `customer_orders` con alias `o`, y sus parámetros."""

    sql: str
    params: tuple


#: Programaciones que todavía no se activaron ni se cancelaron.
_SCHEDULE_PENDING = (
    ScheduleStatus.SCHEDULED, ScheduleStatus.ACTIVATION_PENDING, ScheduleStatus.RESCHEDULED,
)
_PRE_CONFIRMATION = (OrderStatus.DRAFT, OrderStatus.PENDING_CONFIRMATION)
#: Pedidos terminados: nada de lo que muestran estas bandejas les aplica.
_CLOSED = (OrderStatus.COMPLETED, OrderStatus.CANCELLED, OrderStatus.CLOSED, OrderStatus.REVERSED)
_IN_PREPARATION = (FulfillmentStatus.RESERVED, FulfillmentStatus.PREPARING)


def _marcas(valores) -> tuple[str, tuple]:
    params = tuple(v.value for v in valores)
    return ",".join("?" for _ in params), params


def worklist_filter(worklist: OrderWorklist) -> WorklistFilter:
    """El WHERE de una bandeja. Todo valor sale de un enum del dominio y viaja
    como parámetro enlazado; nunca se escribe un estado a mano."""
    if worklist is OrderWorklist.SCHEDULED_PENDING_ACTIVATION:
        programados, p_prog = _marcas(_SCHEDULE_PENDING)
        cerrados, p_cerr = _marcas(_CLOSED)
        return WorklistFilter(
            f"o.schedule_status IN ({programados}) AND o.status NOT IN ({cerrados})",
            p_prog + p_cerr)

    if worklist is OrderWorklist.PENDING_CONFIRMATION:
        previos, p_prev = _marcas(_PRE_CONFIRMATION)
        programados, p_prog = _marcas(_SCHEDULE_PENDING)
        return WorklistFilter(
            f"o.status IN ({previos}) AND o.schedule_status NOT IN ({programados})",
            p_prev + p_prog)

    if worklist is OrderWorklist.PREPARATION_QUEUE:
        en_preparacion, p_prep = _marcas(_IN_PREPARATION)
        return WorklistFilter(
            f"o.status = ? AND o.fulfillment_status IN ({en_preparacion})",
            (OrderStatus.IN_FULFILLMENT.value,) + p_prep)

    if worklist is OrderWorklist.WEIGHT_ADJUSTMENTS_PENDING:
        cerrados, p_cerr = _marcas(_CLOSED)
        return WorklistFilter(
            "o.customer_approval_status = ?"
            f" AND o.status NOT IN ({cerrados})"
            " AND EXISTS (SELECT 1 FROM customer_order_lines l"
            " WHERE l.order_id = o.id AND l.status = ? AND l.substitute_product_id IS NULL)",
            (CustomerApprovalStatus.PENDING.value,) + p_cerr
            + (OrderLineStatus.PENDING_CUSTOMER_APPROVAL.value,))

    if worklist in (OrderWorklist.READY_FOR_PICKUP, OrderWorklist.READY_FOR_DISPATCH):
        # El conjunto de modalidades de recogida es el que APLICA `PickupPolicy`;
        # redeclararlo aquí lo desincronizaría el día que cambie.
        recogida, p_rec = _marcas(
            sorted(PickupPolicy.PICKUP_FULFILLMENT_TYPES, key=lambda tipo: tipo.value))
        base = "o.status = ? AND o.fulfillment_status = ?"
        p_base = (OrderStatus.IN_FULFILLMENT.value, FulfillmentStatus.READY.value)
        if worklist is OrderWorklist.READY_FOR_PICKUP:
            return WorklistFilter(f"{base} AND o.fulfillment_type IN ({recogida})", p_base + p_rec)
        # `DispatchPolicy` exige además que no haya aprobación del cliente
        # pendiente. El repartidor asignado vive en `delivery_jobs`: se asigna en
        # su propia ruta y no se cruza aquí.
        return WorklistFilter(
            f"{base} AND o.fulfillment_type NOT IN ({recogida})"
            " AND o.customer_approval_status <> ?",
            p_base + p_rec + (CustomerApprovalStatus.PENDING.value,))

    raise ValueError(f"Bandeja de pedidos desconocida: {worklist!r}")
