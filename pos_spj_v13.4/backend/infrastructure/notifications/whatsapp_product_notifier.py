"""WhatsAppProductNotifier (PROD-16, §36) — real WhatsApp delivery for the
high-impact product alerts `notification_policy.py` routes to this channel
(quality-blocked, circular recipe, out-of-tolerance yield, meat without
quality profile, duplicate barcode, failed import, discontinued-still-active).

Before this existed, `ProductNotificationGateway` had "a real channel to the
repo's actual WhatsApp service" named as an explicit gap in this bounded
context's own re-audit — only `InMemoryProductNotifier` (test double)
implemented the Protocol. Delega en `backend.infrastructure.integrations.whatsapp_client.WhatsAppClient`,
el mismo que usa Pedidos/Reparto desde la reconstrucción.

SE PERDIÓ LA COLA, y conviene saberlo. El servicio anterior
(`core/services/whatsapp_service.py`) encolaba en un almacén persistente y
offline-first: entregar y reintentar eran problema suyo. Ese servicio
desapareció con `core/` y el contexto canónico de notificaciones no tiene una
cola equivalente — sólo cuentas, plantillas y rutas, que son configuración.

El cliente actual hace una petición directa. Consecuencia concreta: una alerta
que se dispare con el equipo sin conexión NO se reintenta, se pierde. Para
alertas de producto —consultivas, no transaccionales— es un coste asumible
mientras exista; para algo que no pueda perderse, haría falta una bandeja de
salida antes de enrutarlo por aquí. El microservicio ya tiene su propio
despachador de salida, así que ése es el sitio natural de esa cola.

``recipient_ref`` is an E.164-ish phone number, not a user id — WhatsApp has
no other address space. This is a real, narrower scope than the IN_APP
channel (`InAppProductNotifier`, which addresses by user id): resolving
*which staff member's phone number* should receive a given alert is a
recipient-resolution question this phase deliberately does not solve (no
other bounded context in this repo has built that resolver either, confirmed
before writing this — grep for `*whatsapp_notifier*` outside Products found
nothing) — the caller of `ProductNotificationService.notify()` must already
have real phone numbers when it wants WhatsApp delivery.
"""

from __future__ import annotations


class WhatsAppProductNotifier:
    """Implements `ProductNotificationGateway` for the WHATSAPP channel only —
    call `.send()` only when `channel == "WHATSAPP"` (the fan-out gateway
    enforces this).

    PROD-22 (decisión del usuario, 2026-10-10: «cola en el ERP»): ya no envía
    directo. Encola en `product_whatsapp_outbox` dentro de la transacción del
    caso de uso y `ProductWhatsAppOutboxDispatcher` lo entrega después, con
    reintentos; así una alerta disparada sin conexión ya no se pierde y nada
    sale a la red antes de que la operación se confirme.
    """

    def __init__(self, connection) -> None:
        self._conn = connection

    def send(self, *, channel: str, recipient_ref: str, message: str,
             context: dict) -> None:
        from datetime import datetime, timezone

        from backend.shared.ids import new_uuid
        ctx = context or {}
        now = datetime.now(timezone.utc).isoformat(timespec="seconds")
        self._conn.execute(
            "INSERT INTO product_whatsapp_outbox (id, phone, message, alert_type, entity_id, "
            "status, attempts, next_attempt_at, created_at) VALUES (?,?,?,?,?,'PENDING',0,?,?)",
            (new_uuid(), recipient_ref, message, ctx.get("alert_type"), ctx.get("entity_id"),
             now, now))
