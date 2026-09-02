"""OrdersDeliveryWhatsAppClient — Pedidos/Delivery's own integration point
onto the WhatsApp microservice (master prompt §27/§30, both deferred to
"ORD-23" per their own use cases' docstrings: `MarkReadyForPickupUseCase`
(ORD-14) and the customer-approval use cases (ORD-10/11) both say
notification "needs the real WhatsApp gateway, ORD-23").

This is a thin adapter over the REAL, already-working
`core.integrations.whatsapp_client.WhatsAppClient` — a dependency-free
(`urllib`) REST client that already resolves the microservice's base URL and
`X-Internal-Key` from `configuraciones.wa_*` (with `.env` fallback) and
already POSTs to the microservice's live `/api/notify/pedido-listo` and
`/api/notify/send` endpoints. Classified REUSE, not rebuilt — same "wrap the
real, already-solid legacy implementation" reasoning SALES-0's audit applied
to `StockReservationService`.

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

from core.integrations.whatsapp_client import WhatsAppClient


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
