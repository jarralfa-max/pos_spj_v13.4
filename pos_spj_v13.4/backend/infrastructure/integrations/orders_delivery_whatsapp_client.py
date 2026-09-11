"""OrdersDeliveryWhatsAppClient — Pedidos/Delivery's own integration point
onto the WhatsApp microservice (master prompt §27/§30, both deferred to
"ORD-23" per their own use cases' docstrings: `MarkReadyForPickupUseCase`
(ORD-14) and the customer-approval use cases (ORD-10/11) both say
notification "needs the real WhatsApp gateway, ORD-23").

Adaptador fino sobre `backend.infrastructure.integrations.whatsapp_client.
WhatsAppClient`, el cliente REST (sólo `urllib`) hacia el microservicio.

OJO CON LA AUTENTICACIÓN: el cliente que había antes usaba una cabecera
`X-Internal-Key` de texto plano, forma que el microservicio ya NO acepta —
WA-1 la sustituyó por firma HMAC. El cliente actual firma; reconstruirlo "como
estaba" habría dado 401 en cada llamada.

**Never raises.** A WhatsApp delivery failure (microservice down, invalid
phone, network timeout) must never fail the order-side operation that
triggered it — the exact same "best-effort, logged, side effect after the
real transaction already committed" discipline `CheckoutSaleUseCase`'s own
Caja effects already established in this codebase. Every method returns
`True`/`False` for whether the microservice confirmed delivery; callers
surface that as a soft `notification_sent` result field, never as a domain
exception.
"""

from __future__ import annotations

from backend.infrastructure.integrations.whatsapp_client import WhatsAppClient


class OrdersDeliveryWhatsAppClient:
    def __init__(self, client: WhatsAppClient | None = None) -> None:
        self._client = client or WhatsAppClient()

    def notify_ready_for_pickup(
        self, *, phone: str, order_number: str, branch_name: str = "",
    ) -> bool:
        """§30's own second step: "listo -> notificación -> validación de
        identidad -> cobro si pendiente -> entrega". Reuses the
        microservice's dedicated `/api/notify/pedido-listo` template rather
        than a generic message."""
        if not (phone or "").strip():
            return False
        try:
            return self._client.notificar_pedido_listo(phone, order_number or "", branch_name)
        except Exception:
            return False

    def notify_customer_approval_required(
        self, *, phone: str, order_number: str, reason: str,
    ) -> bool:
        """§27's own second step for a weight-adjustment/substitution that
        needs the customer's OK. No dedicated microservice template exists
        for this case (unlike pickup/deposit/quote), so this uses the
        generic `/api/notify/send`. The two-way conversation (customer
        replies to accept/reject) is the WhatsApp microservice's own
        `flows/` concern, not this ERP-side outbound trigger."""
        if not (phone or "").strip():
            return False
        message = (
            f"Hola, tu pedido {order_number or ''} requiere tu aprobación: {reason}. "
            "Por favor contacta a la sucursal para confirmar."
        )
        try:
            return self._client.enviar_mensaje(phone, message)
        except Exception:
            return False

    def send_message(self, *, phone: str, message: str) -> bool:
        """ORD-26: a genuinely generic outbound message — used by
        `DeliveryNotificationPolicy`'s own already-composed text (dispatched/
        completed/failed), unlike `notify_customer_approval_required`, whose
        wording is hardcoded to the approval-required case specifically."""
        if not (phone or "").strip():
            return False
        try:
            return self._client.enviar_mensaje(phone, message)
        except Exception:
            return False
