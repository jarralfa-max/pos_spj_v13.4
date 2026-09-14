"""Bandejas de reparto: UNA definición, la usan la lista y su badge.

POR QUÉ EXISTE
--------------
"Entregas activas" y "Entregas fallidas" tenían badge —y un KPI en el resumen—,
pero contaban sobre `customer_orders`, y eso estaba mal:

- `fulfillment_status='FAILED'` sólo lo escribe `mark_reservation_failed()`, la
  reserva de INVENTARIO fallida. El KPI "Entregas fallidas" contaba reservas
  fallidas.
- Un intento de entrega fallido NO toca el pedido: `RecordDeliveryAttemptUseCase`
  registra el intento en el trabajo y el pedido se queda en `DISPATCHED`.
  "Entregas activas" contaba también las que ya habían fallado.

La fuente es `delivery_jobs.status`, que escribe el propio `DeliveryJob`:
`record_attempt()` llama a `mark_delivered()` o a `mark_failed()` según el
resultado. Los estados de cada bandeja siguen la tabla de transiciones de
`DeliveryLifecyclePolicy`.

LO QUE NO ESTÁ AQUÍ
-------------------
Reentregas, cobros, liquidaciones y rutas viven en otras tablas
(`redelivery_requests`, `driver_cash_collections`, `driver_settlements`,
`delivery_routes`). Y cuidado con leer "reentregas" del trabajo: aprobar una
reentrega crea un trabajo NUEVO y el original se queda en `REDELIVERY_PENDING`
para siempre, así que ese estado no dice si la solicitud sigue pendiente.
"""

from __future__ import annotations

from enum import Enum

from backend.application.orders_delivery.queries.order_worklists import WorklistFilter
from backend.domain.orders_delivery.enums import DeliveryStatus


class DeliveryWorklist(str, Enum):
    """Los valores de las dos que tienen badge coinciden con su clave en el sidebar."""

    PENDING_DRIVER_ASSIGNMENT = "pending_driver_assignment"
    ACTIVE_DELIVERIES = "active_deliveries"
    FAILED_DELIVERIES = "failed_deliveries"
    RETURNED_TO_BRANCH = "returned_to_branch"


_ESTADOS: dict[DeliveryWorklist, tuple[DeliveryStatus, ...]] = {
    DeliveryWorklist.PENDING_DRIVER_ASSIGNMENT: (DeliveryStatus.PENDING_ASSIGNMENT,),
    # Despachado y todavía sin resultado: DISPATCHED -> IN_TRANSIT -> ARRIVED ->
    # DELIVERY_ATTEMPT, en la tabla de transiciones.
    DeliveryWorklist.ACTIVE_DELIVERIES: (
        DeliveryStatus.DISPATCHED, DeliveryStatus.IN_TRANSIT,
        DeliveryStatus.ARRIVED, DeliveryStatus.DELIVERY_ATTEMPT),
    # FAILED espera decisión —reentrega o retorno— y sale de aquí al tomarla.
    DeliveryWorklist.FAILED_DELIVERIES: (DeliveryStatus.FAILED,),
    # `ReturnToBranchUseCase` llama a start_return() y complete_return() seguidos:
    # RETURNING es transitorio, y se incluye por si un retorno queda a medias.
    DeliveryWorklist.RETURNED_TO_BRANCH: (
        DeliveryStatus.RETURNING, DeliveryStatus.RETURNED_TO_BRANCH),
}


def delivery_worklist_filter(worklist: DeliveryWorklist) -> WorklistFilter:
    """Condición sobre `delivery_jobs` con alias `j`. Los estados salen del enum y
    viajan como parámetros enlazados."""
    try:
        estados = _ESTADOS[worklist]
    except KeyError as exc:
        raise ValueError(f"Bandeja de reparto desconocida: {worklist!r}") from exc
    marcas = ",".join("?" for _ in estados)
    return WorklistFilter(f"j.status IN ({marcas})", tuple(estado.value for estado in estados))
