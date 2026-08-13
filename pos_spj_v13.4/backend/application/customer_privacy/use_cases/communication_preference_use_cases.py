"""CustomerCommunicationPreference use cases: create-or-update (upsert,
since it is a 1:1 settings record per customer).

Gated by ``COMMUNICATION_PREFERENCE_MANAGE`` (CRM-9 retroactive addition —
see backend/application/customers/permissions.py).
"""

from __future__ import annotations

from backend.application.customers.authorization import CustomerAuthorizationPolicy
from backend.application.customers.permissions import CustomerPermissions
from backend.application.customer_privacy.result import CustomerPrivacyResult
from backend.domain.customer_privacy.entities.customer_communication_preference import (
    CustomerCommunicationPreference,
)
from backend.domain.customer_privacy.enums import PreferredChannel
from backend.domain.customer_privacy.events import CustomerPrivacyEvents
from backend.domain.customer_privacy.exceptions import CustomerPrivacyDomainError
from backend.domain.customers.exceptions import CustomerDomainError
from backend.infrastructure.db.repositories.customer_privacy.unit_of_work import (
    CustomerPrivacyUnitOfWork,
)


class SetCommunicationPreferenceUseCase:
    def __init__(self, authorization: CustomerAuthorizationPolicy | None = None) -> None:
        self._auth = authorization or CustomerAuthorizationPolicy()

    def execute(
        self, connection, *, actor_user_id: str, customer_id: str, operation_id: str,
        preferred_channel: str | None = None, preferred_language: str | None = None,
        contact_hours_start: str | None = None, contact_hours_end: str | None = None,
        allow_operational: bool | None = None, allow_marketing: bool | None = None,
        allow_promotions: bool | None = None, allow_reminders: bool | None = None,
    ) -> CustomerPrivacyResult:
        try:
            self._auth.require(actor_user_id, CustomerPermissions.COMMUNICATION_PREFERENCE_MANAGE)
        except CustomerDomainError as exc:
            return CustomerPrivacyResult.fail(str(exc), "PERMISSION_DENIED",
                                              operation_id=operation_id)
        with CustomerPrivacyUnitOfWork(connection) as uow:
            preference = uow.preferences.get_by_customer_id(customer_id)
            is_new = preference is None
            try:
                if is_new:
                    preference = CustomerCommunicationPreference.create(
                        customer_id,
                        preferred_channel=(PreferredChannel(preferred_channel)
                                           if preferred_channel else PreferredChannel.WHATSAPP),
                        preferred_language=preferred_language or "es",
                        updated_by_user_id=actor_user_id)
                preference.update(
                    updated_by_user_id=actor_user_id,
                    preferred_channel=(PreferredChannel(preferred_channel)
                                       if preferred_channel else None),
                    preferred_language=preferred_language,
                    contact_hours_start=contact_hours_start, contact_hours_end=contact_hours_end,
                    allow_operational=allow_operational, allow_marketing=allow_marketing,
                    allow_promotions=allow_promotions, allow_reminders=allow_reminders)
            except (CustomerPrivacyDomainError, ValueError) as exc:
                return CustomerPrivacyResult.fail(str(exc), "VALIDATION",
                                                  operation_id=operation_id)
            if is_new:
                uow.preferences.save(preference)
            else:
                uow.preferences.update(preference)
            uow.audit.record(action=CustomerPrivacyEvents.COMMUNICATION_PREFERENCE_UPDATED,
                             actor_user_id=actor_user_id, customer_id=customer_id,
                             operation_id=operation_id)
        return CustomerPrivacyResult.ok("Preferencia de comunicación actualizada",
                                        entity_id=preference.id, operation_id=operation_id)
