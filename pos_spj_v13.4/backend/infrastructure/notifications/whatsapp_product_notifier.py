"""WhatsAppProductNotifier (PROD-16, §36) — real WhatsApp delivery for the
high-impact product alerts `notification_policy.py` routes to this channel
(quality-blocked, circular recipe, out-of-tolerance yield, meat without
quality profile, duplicate barcode, failed import, discontinued-still-active).

Before this existed, `ProductNotificationGateway` had "a real channel to the
repo's actual WhatsApp service" named as an explicit gap in this bounded
context's own re-audit — only `InMemoryProductNotifier` (test double)
implemented the Protocol. Delegates to the real, canonical
`core/services/whatsapp_service.py::WhatsAppService` (the same service every
other module's WhatsApp alerts go through) rather than talking to any
transport directly — `send_message` enqueues onto that service's own
persistent, offline-first queue; delivery timing/retries are its job, not
this notifier's.

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
    enforces this)."""

    def __init__(self, connection) -> None:
        from core.services.whatsapp_service import WhatsAppService
        self._service = WhatsAppService(conn=connection)

    def send(self, *, channel: str, recipient_ref: str, message: str,
             context: dict) -> None:
        branch_id = (context or {}).get("branch_id")
        self._service.send_message(
            branch_id=branch_id, phone_number=recipient_ref, message=message)
