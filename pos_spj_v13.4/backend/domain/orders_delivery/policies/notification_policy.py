"""DeliveryNotificationPolicy (master prompt ORD-26 "4. Policies") — the
single decision point for "does this delivery event need a customer
message, and/or an internal staff alert, and with what text". ORD-23 wired
two customer triggers (approval-required, ready-for-pickup) directly inline
inside their own use cases with no shared decision table; this phase adds
more triggers (dispatched, completed, failed) and, this time, centralizes
the "which event -> which message/channel" mapping here instead of
scattering another `if event == ...` per use case.

Deliberately NOT a full configurable/DB-backed rules engine like Cash
Register's own CASH-20 (`cash_alert_rules`/`cash_notification_jobs`, its own
schema+dispatcher) — that is real, substantial infrastructure this phase's
scope does not extend to duplicating for a second bounded context. This is
a pure, static, testable policy; an admin-configurable version is a future
phase's job if the business actually asks for per-branch overrides.
"""

from __future__ import annotations

from backend.domain.orders_delivery.events import DeliveryEvents

_CUSTOMER_MESSAGE_TEMPLATES: dict[str, str] = {
    DeliveryEvents.DISPATCHED: "Tu pedido {order_number} salió de la sucursal y va en camino.",
    DeliveryEvents.COMPLETED: "Tu pedido {order_number} fue entregado. ¡Gracias por tu compra!",
    DeliveryEvents.FAILED: "No pudimos entregar tu pedido {order_number}. Nos pondremos en "
                           "contacto para reprogramar.",
}

_INTERNAL_ALERT_EVENTS: frozenset[str] = frozenset({
    DeliveryEvents.FAILED,
    DeliveryEvents.DRIVER_SETTLEMENT_DIFFERENCE_DETECTED,
})


class DeliveryNotificationPolicy:
    @staticmethod
    def customer_message(event_name: str, **context: str) -> str | None:
        """Returns the customer-facing WhatsApp text for `event_name`, or
        `None` if this event has no customer message (most events don't —
        only the ones a customer would actually want to know about)."""
        template = _CUSTOMER_MESSAGE_TEMPLATES.get(event_name)
        if template is None:
            return None
        return template.format(**context)

    @staticmethod
    def requires_internal_alert(event_name: str) -> bool:
        """Whether branch/ops staff should get an in-app alert for this
        event — currently only failures and money-reconciliation
        differences, the two classes of event that need a HUMAN to act,
        not just a customer FYI."""
        return event_name in _INTERNAL_ALERT_EVENTS
