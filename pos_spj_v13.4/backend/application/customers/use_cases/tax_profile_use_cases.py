"""UpdateCustomerTaxProfileUseCase (§15, §58) — upsert semantics: one profile
per customer, created on first write.
"""

from __future__ import annotations

import json

from backend.application.customers.authorization import CustomerAuthorizationPolicy
from backend.application.customers.permissions import CustomerPermissions
from backend.application.customers.result import CustomerResult
from backend.domain.customers.entities.customer_tax_profile import CustomerTaxProfile
from backend.domain.customers.events import CustomerEvents, build_event_payload
from backend.domain.customers.exceptions import CustomerDomainError
from backend.infrastructure.db.repositories.customers.unit_of_work import CustomerUnitOfWork


class UpdateCustomerTaxProfileUseCase:
    def __init__(self, authorization: CustomerAuthorizationPolicy | None = None) -> None:
        self._auth = authorization or CustomerAuthorizationPolicy()

    def execute(
        self, connection, *, actor_user_id: str, customer_id: str, operation_id: str,
        tax_identifier: str | None = None, legal_name: str | None = None,
        tax_regime: str | None = None, fiscal_postal_code: str | None = None,
        default_cfdi_use: str | None = None, billing_email: str | None = None,
    ) -> CustomerResult:
        try:
            self._auth.require(actor_user_id, CustomerPermissions.TAX_PROFILE_EDIT)
        except CustomerDomainError as exc:
            return CustomerResult.fail(str(exc), "PERMISSION_DENIED", operation_id=operation_id)
        with CustomerUnitOfWork(connection) as uow:
            if uow.customers.get(customer_id) is None:
                return CustomerResult.fail("El cliente no existe", "NOT_FOUND",
                                           operation_id=operation_id)
            profile = uow.tax_profiles.get_for_customer(customer_id)
            if profile is None:
                profile = CustomerTaxProfile.create(
                    customer_id, tax_identifier=tax_identifier or "",
                    legal_name=legal_name or "", tax_regime=tax_regime or "",
                    fiscal_postal_code=fiscal_postal_code or "",
                    default_cfdi_use=default_cfdi_use or "", billing_email=billing_email)
                uow.tax_profiles.save(profile)
            else:
                for field_name, value in (
                    ("tax_identifier", tax_identifier), ("legal_name", legal_name),
                    ("tax_regime", tax_regime), ("fiscal_postal_code", fiscal_postal_code),
                    ("default_cfdi_use", default_cfdi_use), ("billing_email", billing_email),
                ):
                    if value is not None:
                        setattr(profile, field_name, value)
                uow.tax_profiles.update(profile)
            uow.audit.record(action=CustomerEvents.TAX_PROFILE_UPDATED,
                             actor_user_id=actor_user_id, customer_id=customer_id,
                             reason="actualización de perfil fiscal", operation_id=operation_id)
            payload = build_event_payload(
                CustomerEvents.TAX_PROFILE_UPDATED, operation_id=operation_id,
                customer_id=customer_id, user_id=actor_user_id)
            uow.outbox.enqueue(payload["event_id"], CustomerEvents.TAX_PROFILE_UPDATED,
                               json.dumps(payload), operation_id)
        return CustomerResult.ok("Perfil fiscal actualizado", entity_id=profile.id,
                                 operation_id=operation_id)
