"""OrdersDeliveryBadgeQueryService — branch-scoped sidebar badge counters
(master prompt §68: "Mostrar badges desde QueryServices", never computed
inline by the UI). Queries the NEW canonical `customer_orders` table built in
ORD-3, not the legacy `delivery_orders` (`core/services/order_badge_service.py`
keeps serving the live `modulos/delivery.py` sidebar off the legacy schema —
this is a parallel, not-yet-wired badge source for the new skeleton built in
ORD-4).

Defensive like its legacy counterpart: a missing/older schema degrades to 0,
it never raises into the UI.
"""

from __future__ import annotations

from backend.application.orders_delivery.queries.delivery_worklists import (
    DeliveryWorklist,
    delivery_worklist_filter,
)
from backend.domain.orders_delivery.policies.notification_policy import DELIVERY_ALERT_TYPES
from backend.application.orders_delivery.queries.order_worklists import (
    OrderWorklist,
    worklist_filter,
)

#: Badges que SON bandejas de pedido: su definición vive en `order_worklists`, la
#: misma que usa la lista. Ese módulo documenta los tres que estaban mal
#: (preparación, ajustes de peso, programados).
_ORDER_WORKLIST_BADGES = (
    OrderWorklist.SCHEDULED_PENDING_ACTIVATION,
    OrderWorklist.PENDING_CONFIRMATION,
    OrderWorklist.PREPARATION_QUEUE,
    OrderWorklist.WEIGHT_ADJUSTMENTS_PENDING,
)

#: Badges que son bandejas de REPARTO: cuentan `delivery_jobs`, con la misma
#: definición que su lista (`delivery_worklists`).
_DELIVERY_WORKLIST_BADGES = (
    DeliveryWorklist.ACTIVE_DELIVERIES,
    DeliveryWorklist.FAILED_DELIVERIES,
)


class OrdersDeliveryBadgeQueryService:
    def __init__(self, db) -> None:
        self.db = db

    def get_badge_counts(self, branch_id: str, *,
                         recipient_user_id: str | None = None) -> dict[str, int]:
        counts: dict[str, int] = {}
        for worklist in _ORDER_WORKLIST_BADGES:
            filtro = worklist_filter(worklist)
            counts[worklist.value] = self._safe_count(
                "SELECT COUNT(*) FROM customer_orders o"
                f" WHERE o.branch_id=? AND ({filtro.sql})",
                (branch_id, *filtro.params))

        # "Entregas activas" y "fallidas" son bandejas de REPARTO. Antes contaban
        # sobre `customer_orders`: `fulfillment_status='FAILED'` sólo lo escribe la
        # reserva de inventario fallida, y un intento de entrega fallido deja el
        # pedido en DISPATCHED. Ver `delivery_worklists`.
        for worklist in _DELIVERY_WORKLIST_BADGES:
            filtro = delivery_worklist_filter(worklist)
            counts[worklist.value] = self._safe_count(
                "SELECT COUNT(*) FROM delivery_jobs j"
                f" WHERE j.branch_id=? AND ({filtro.sql})",
                (branch_id, *filtro.params))
        # ORD-21 built driver_settlements and ORD-26 built the
        # notification_inbox-backed internal alert — both were 0 only because
        # neither existed yet when ORD-4 wrote this service.
        counts["settlements_pending_review"] = self._safe_count(
            "SELECT COUNT(*) FROM driver_settlements "
            "WHERE branch_id=? AND status='PENDING_REVIEW'",
            (branch_id,))
        # La bandeja es POR PERSONA: el notificador escribe un renglón por cada
        # destinatario (cada admin/gerente). Con `recipient_user_id` se cuentan las
        # alertas sin leer de ESA persona, lo mismo que su pantalla de Alertas. Sin
        # usuario se cuentan renglones de la sucursal, y eso suma una vez por
        # destinatario: sirve de volumen, no de "pendientes".
        tipos = sorted(DELIVERY_ALERT_TYPES)
        destinatario = (recipient_user_id,) if recipient_user_id else ()
        counts["critical_alerts"] = self._safe_count(
            "SELECT COUNT(*) FROM notification_inbox"
            f" WHERE sucursal_id=? AND tipo IN ({','.join('?' for _ in tipos)})"
            " AND leido=0" + (" AND empleado_id=?" if destinatario else ""),
            (branch_id, *tipos, *destinatario))
        return counts

    def _safe_count(self, sql: str, params: tuple) -> int:
        try:
            row = self.db.execute(sql, params).fetchone()
            return int(row[0] or 0) if row else 0
        except Exception:
            return 0
