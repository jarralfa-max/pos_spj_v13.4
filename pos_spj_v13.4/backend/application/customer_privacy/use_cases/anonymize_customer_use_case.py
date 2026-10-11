"""AnonymizeCustomerUseCase — the one place Customer Privacy and Customer
Master touch (§44, §74). Completes an ``ANONYMIZATION``/``CANCELLATION``
(erasure) ``CustomerPrivacyRequest``.

Two CRM-2-built mechanisms get their second real consumer here (the first
was CRM-8's credit-limit override):

- ``CustomerAuthorizationPolicy.authorize_exception()`` /
  ``CustomerAuthorizationGrant`` — §74 explicitly lists "anonimización" as
  one of the extraordinary actions requiring a second, distinct
  authorizer. ``authorized_by`` (the caller) must differ from
  ``requested_by`` (who logged the original privacy request).
- ``CustomerSegregationOfDutiesPolicy.enforce_anonymization_preserves_
  audit()`` — "quien anonimiza no borra auditoría" (§73). This use case
  never issues a DELETE against any audit table, so the assertion it makes
  (``audit_retained=True``) is honest, not a rubber stamp.

**Scope of what is actually redacted** (§44: "Anonimización respeta
obligaciones fiscales, ventas históricas, CxC, auditoría, prevención de
fraude, retención legal"): only ``Customer``'s own direct name-presentation
fields (``display_name``, ``first_name``, ``last_name``,
``second_last_name``, ``commercial_name``) are scrubbed. ``legal_name`` is
deliberately left untouched (fiscal/RFC ties — "obligaciones fiscales").
``CustomerContactPerson``/``CustomerAddress``/``CustomerTaxProfile`` child
records, and anything in Ventas/Finanzas, are NOT touched here — reaching
into those is explicitly out of this bounded context's ownership (same
"no ledger paralelo" boundary CRM-8 already respected for CxC) and a
larger, separately-scoped effort. ``Customer.mark_anonymized()`` (built in
CRM-3 specifically for this call) flips ``status`` to ``ANONYMIZED``; it
does not implement anonymization logic itself, so this use case is exactly
the caller CRM-3 was waiting for.

Auditoría CRM F15 (2026-10-09): la operación prometía más de lo que hacía —
dejaba en claro teléfono, correo y domicilios de los contactos. Contactos y
domicilios son hijos del PROPIO maestro de clientes, así que ahora también se
tratan, con esta política:

* contactos: nombre → «Contacto anonimizado»; teléfono, correo, puesto y área
  se borran; quedan inactivos;
* domicilios de entrega, comerciales y personales: calle, números, colonia,
  referencias y coordenadas se borran (se conservan código postal, municipio y
  estado: no identifican a la persona y sostienen estadística por zona);
* SE CONSERVAN, por obligación fiscal: el perfil fiscal (RFC, razón social) y
  los domicilios FISCAL/BILLING — igual que ya se conservaba ``legal_name``.

Lo que vive en otros contextos (ventas, CxC, notas del CRM, conversaciones de
WhatsApp) no se toca aquí; queda listado en la reauditoría como pendiente.

Atomicity: both bounded contexts (customer_privacy, customers) write to
the same connection in one transaction — same shared-connection,
manual-commit pattern as CRM-4's ``ConvertLeadUseCase``.
"""

from __future__ import annotations

import json

from backend.application.customer_privacy.result import CustomerPrivacyResult
from backend.application.customers.authorization import CustomerAuthorizationPolicy
from backend.application.customers.permissions import CustomerPermissions
from backend.domain.customer_privacy.events import CustomerPrivacyEvents, build_event_payload
from backend.domain.customer_privacy.exceptions import CustomerPrivacyDomainError
from backend.domain.customers.exceptions import CustomerDomainError
from backend.domain.customers.policies.segregation_of_duties_policy import (
    CustomerSegregationOfDutiesPolicy,
)
from backend.infrastructure.db.repositories.customer_privacy.unit_of_work import (
    CustomerPrivacyUnitOfWork,
)
from backend.infrastructure.db.repositories.customers.unit_of_work import CustomerUnitOfWork

_ANONYMIZED_PLACEHOLDER = "Cliente anonimizado"
_ANONYMIZED_CONTACT = "Contacto anonimizado"
#: Domicilios que se conservan por obligación fiscal (facturas emitidas).
_FISCAL_ADDRESS_TYPES = ("FISCAL", "BILLING")


def _scrub_contacts_and_addresses(customers_uow, customer_id: str) -> None:
    for contact in customers_uow.contacts.list_for_customer(customer_id):
        contact.first_name = _ANONYMIZED_CONTACT
        contact.last_name = ""
        contact.job_title = ""
        contact.department = ""
        contact.phone_e164 = None
        contact.email = None
        contact.status = "INACTIVE"
        customers_uow.contacts.update(contact)
    for address in customers_uow.addresses.list_for_customer(customer_id):
        if getattr(address.address_type, "value", address.address_type) in _FISCAL_ADDRESS_TYPES:
            continue
        address.street = "Anonimizado"
        address.external_number = ""
        address.internal_number = ""
        address.neighborhood = ""
        address.locality = ""
        address.references = ""
        address.latitude = None
        address.longitude = None
        customers_uow.addresses.update(address)


class AnonymizeCustomerUseCase:
    def __init__(self, authorization: CustomerAuthorizationPolicy | None = None) -> None:
        self._auth = authorization or CustomerAuthorizationPolicy()
        self._sod = CustomerSegregationOfDutiesPolicy()

    def execute(
        self, connection, *, authorizer_user_id: str, request_id: str, operation_id: str,
        reason: str,
    ) -> CustomerPrivacyResult:
        privacy_uow = CustomerPrivacyUnitOfWork(connection)
        customers_uow = CustomerUnitOfWork(connection)
        try:
            result = self._anonymize(privacy_uow, customers_uow, authorizer_user_id=authorizer_user_id,
                                     request_id=request_id, operation_id=operation_id, reason=reason)
        except Exception:
            connection.rollback()
            raise
        if result.success:
            connection.commit()
        else:
            connection.rollback()
        return result

    def _anonymize(
        self, privacy_uow: CustomerPrivacyUnitOfWork, customers_uow: CustomerUnitOfWork, *,
        authorizer_user_id: str, request_id: str, operation_id: str, reason: str,
    ) -> CustomerPrivacyResult:
        request = privacy_uow.requests.get(request_id)
        if request is None:
            return CustomerPrivacyResult.fail("La solicitud no existe", "NOT_FOUND",
                                              operation_id=operation_id)
        if not request.requires_anonymization_workflow():
            return CustomerPrivacyResult.fail(
                f"La solicitud {request.code} no es de anonimización/cancelación", "VALIDATION",
                operation_id=operation_id)
        if request.status.value != "IN_PROGRESS":
            return CustomerPrivacyResult.fail(
                f"La solicitud debe estar IN_PROGRESS (está {request.status.value})",
                "VALIDATION", operation_id=operation_id)

        try:
            grant = self._auth.authorize_exception(
                authorizer_user_id=authorizer_user_id,
                requested_by=request.logged_by_user_id or authorizer_user_id,
                permission_code=CustomerPermissions.PRIVACY_REQUEST_APPROVE,
                operation_id=operation_id, reason=reason)
            self._sod.enforce_anonymization_preserves_audit(audit_retained=True)
        except CustomerDomainError as exc:
            return CustomerPrivacyResult.fail(str(exc), "PERMISSION_DENIED",
                                              operation_id=operation_id)

        customer = customers_uow.customers.get(request.customer_id)
        if customer is None:
            return CustomerPrivacyResult.fail("El cliente no existe", "NOT_FOUND",
                                              operation_id=operation_id)

        customer.display_name = _ANONYMIZED_PLACEHOLDER
        customer.first_name = ""
        customer.last_name = ""
        customer.second_last_name = ""
        customer.commercial_name = ""
        customer.mark_anonymized()
        customers_uow.customers.update(customer)
        _scrub_contacts_and_addresses(customers_uow, customer.id)

        try:
            request.complete(f"Anonimizado por {grant.authorized_by}: {reason}")
        except CustomerPrivacyDomainError as exc:
            return CustomerPrivacyResult.fail(str(exc), "VALIDATION", operation_id=operation_id)
        privacy_uow.requests.update(request)

        privacy_uow.audit.record(
            action=CustomerPrivacyEvents.CUSTOMER_ANONYMIZED, actor_user_id=grant.requested_by,
            customer_id=customer.id, request_id=request.id, authorized_by_user_id=grant.authorized_by,
            reason=reason, operation_id=operation_id)
        payload = build_event_payload(
            CustomerPrivacyEvents.CUSTOMER_ANONYMIZED, operation_id=operation_id,
            customer_id=customer.id, request_id=request.id, user_id=grant.authorized_by,
            requested_by=grant.requested_by)
        privacy_uow.outbox.enqueue(payload["event_id"], CustomerPrivacyEvents.CUSTOMER_ANONYMIZED,
                                   json.dumps(payload), operation_id)

        return CustomerPrivacyResult.ok("Cliente anonimizado", entity_id=request.id,
                                        operation_id=operation_id, customer_id=customer.id)
