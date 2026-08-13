"""CustomerCommunicationPreferenceQueryService — read side for the
customer's communication preference settings. Reads only; never mutates.
Consumed by WhatsApp/Notification Management before sending a message
(§44: "WhatsApp y Notification Management la consumen") — those modules
call this instead of reading the table directly.
"""

from __future__ import annotations

from backend.application.customers.authorization import CustomerAuthorizationPolicy
from backend.application.customers.permissions import CustomerPermissions
from backend.domain.customer_privacy.entities.customer_communication_preference import (
    CustomerCommunicationPreference,
)
from backend.infrastructure.db.repositories.customer_privacy.unit_of_work import (
    CustomerPrivacyUnitOfWork,
)


class CustomerCommunicationPreferenceQueryService:
    def __init__(self, connection, authorization: CustomerAuthorizationPolicy | None = None) -> None:
        self._uow = CustomerPrivacyUnitOfWork(connection)
        self._auth = authorization or CustomerAuthorizationPolicy()

    def get(self, customer_id: str, *,
            actor_user_id: str) -> CustomerCommunicationPreference | None:
        self._auth.require(actor_user_id, CustomerPermissions.COMMUNICATION_PREFERENCE_VIEW)
        return self._uow.preferences.get_by_customer_id(customer_id)
