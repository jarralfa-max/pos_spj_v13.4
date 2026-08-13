"""CustomerConsentQueryService — read side for consent records. Reads
only; never mutates. Flat permission (``CONSENT_VIEW``) — CRM-2's catalog
defines no OWN/TEAM axis for consent, same precedent as CRM-6's Activities/
Tasks/Notes.
"""

from __future__ import annotations

from backend.application.customers.authorization import CustomerAuthorizationPolicy
from backend.application.customers.permissions import CustomerPermissions
from backend.domain.customer_privacy.entities.customer_consent import CustomerConsent
from backend.infrastructure.db.repositories.customer_privacy.unit_of_work import (
    CustomerPrivacyUnitOfWork,
)


class CustomerConsentQueryService:
    def __init__(self, connection, authorization: CustomerAuthorizationPolicy | None = None) -> None:
        self._uow = CustomerPrivacyUnitOfWork(connection)
        self._auth = authorization or CustomerAuthorizationPolicy()

    def list_for_customer(self, customer_id: str, *, actor_user_id: str) -> list[CustomerConsent]:
        self._auth.require(actor_user_id, CustomerPermissions.CONSENT_VIEW)
        return self._uow.consents.list_for_customer(customer_id)

    def get_latest(self, customer_id: str, consent_type: str, *,
                    actor_user_id: str) -> CustomerConsent | None:
        self._auth.require(actor_user_id, CustomerPermissions.CONSENT_VIEW)
        return self._uow.consents.get_latest(customer_id, consent_type)

    def is_active(self, customer_id: str, consent_type: str, *, actor_user_id: str) -> bool:
        """Convenience check other bounded contexts (WhatsApp, Notification
        Management) can call before sending a marketing/WhatsApp message —
        "No inferir consentimiento por tener teléfono/correo" (§44): this is
        the one sanctioned way to check, never a shortcut around it."""
        self._auth.require(actor_user_id, CustomerPermissions.CONSENT_VIEW)
        latest = self._uow.consents.get_latest(customer_id, consent_type)
        return latest is not None and latest.is_active()
