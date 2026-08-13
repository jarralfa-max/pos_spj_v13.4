"""CustomerWhatsAppSummaryQuery (§49): "CRM muestra identidad vinculada,
consentimiento, última conversación, conversaciones abiertas, handoff;
WhatsApp conserva mensajes... no duplicar contenido completo de mensajes."

**Scope actually deliverable today vs. deferred**: only ``has_active_
whatsapp_consent`` is real — it reuses CRM-9's
``CustomerConsentQueryService.is_active()`` (keyed on this bounded
context's own UUIDv7 ``customer_id``, so unlike every other CRM-13
integration this ONE has no identity-mismatch gap: consent already lives in
the shared app DB, correctly keyed).

``last_conversation_at``/``open_conversations_count``/``handoff_pending``
are deliberately always ``None``/``0``/``False`` here, not omitted from the
view — conversation/handoff state lives entirely inside the WhatsApp
microservice's OWN separate SQLite database
(``whatsapp_service/state/conversation.py``'s ``ConversationStore``, file
``whatsapp_service/data/conversations.db``), a different physical database
this bounded context has no connection to. Per CLAUDE.md §14, WhatsApp is
architected as an independent microservice reachable only via REST/EventBus
— reading its DB file directly would violate that boundary the same way
reaching into another module's *shared-DB* table would violate a bounded-
context line. Populating these three fields for real needs either a REST
call to ``whatsapp_service/erp/bridge.py`` (auth, timeout, offline handling
— a materially larger integration than one query service) or an outbound
projection WhatsApp itself publishes, neither of which exists yet. Left as
a documented gap, not fabricated with a fake bridge.
"""

from __future__ import annotations

from dataclasses import dataclass

from backend.application.customers.authorization import CustomerAuthorizationPolicy
from backend.application.customers.permissions import CustomerPermissions
from backend.application.customer_privacy.queries.customer_consent_query_service import (
    CustomerConsentQueryService,
)
from backend.domain.customer_privacy.enums import ConsentType


@dataclass(frozen=True)
class CustomerWhatsAppSummary:
    customer_id: str
    has_active_whatsapp_consent: bool
    last_conversation_at: str | None
    open_conversations_count: int
    handoff_pending: bool


class CustomerWhatsAppSummaryQuery:
    def __init__(self, connection, authorization: CustomerAuthorizationPolicy | None = None) -> None:
        self._connection = connection
        self._auth = authorization or CustomerAuthorizationPolicy()

    def get_summary(self, customer_id: str, *, actor_user_id: str) -> CustomerWhatsAppSummary:
        self._auth.require(actor_user_id, CustomerPermissions.WHATSAPP_VIEW)
        consent_service = CustomerConsentQueryService(self._connection, self._auth)
        has_consent = consent_service.is_active(
            customer_id, ConsentType.WHATSAPP.value, actor_user_id=actor_user_id)
        return CustomerWhatsAppSummary(
            customer_id=customer_id, has_active_whatsapp_consent=has_consent,
            last_conversation_at=None, open_conversations_count=0, handoff_pending=False)
