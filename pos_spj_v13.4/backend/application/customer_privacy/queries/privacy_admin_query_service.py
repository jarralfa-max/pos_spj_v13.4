"""PrivacyAdminQueryService (§41-44, CRM-43) — bandejas de privacidad:
todas las solicitudes (no sólo las de un estado), el catálogo de retención
y el historial de avisos de un cliente.
"""

from __future__ import annotations

from backend.application.customers.authorization import CustomerAuthorizationPolicy
from backend.application.customers.permissions import CustomerPermissions
from backend.infrastructure.db.repositories.customer_privacy.unit_of_work import (
    CustomerPrivacyUnitOfWork,
)
from backend.infrastructure.db.repositories.customers.customer_channel_history_repository import (
    CustomerChannelHistoryRepository,
)


class PrivacyAdminQueryService:
    def __init__(self, connection, authorization: CustomerAuthorizationPolicy | None = None) -> None:
        self._uow = CustomerPrivacyUnitOfWork(connection)
        self._channels = CustomerChannelHistoryRepository(connection)
        self._auth = authorization or CustomerAuthorizationPolicy()

    def requests(self, *, actor_user_id: str):
        self._auth.require(actor_user_id, CustomerPermissions.PRIVACY_REQUEST_VIEW)
        return self._uow.requests.list_all()

    def request_trail(self, request_id: str, *, actor_user_id: str) -> list[dict]:
        self._auth.require(actor_user_id, CustomerPermissions.PRIVACY_REQUEST_VIEW)
        return self._uow.audit.list_for_request(request_id)

    def retention_policies(self, *, actor_user_id: str):
        self._auth.require(actor_user_id, CustomerPermissions.SETTINGS_VIEW)
        return self._uow.retention_policies.list_all()

    def notification_history(self, customer_id: str, *, actor_user_id: str) -> list[dict]:
        self._auth.require(actor_user_id, CustomerPermissions.WHATSAPP_VIEW)
        return self._channels.whatsapp_messages(customer_id)
