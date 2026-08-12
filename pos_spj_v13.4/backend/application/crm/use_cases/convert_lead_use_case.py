"""ConvertLeadUseCase (§18) — the one place Leads (CRM) and Customer Master
touch each other.

Flow (§18): Validar lead (debe estar QUALIFIED) → Buscar coincidencias →
Seleccionar (``link_to_customer_id``) o crear Customer → Crear cuenta/
contacto → [Crear oportunidad opcional — **no implementado aquí**, CRM-5 no
existe todavía; el evento ``CRM_LEAD_CONVERTED`` lleva ``customer_id`` en su
payload precisamente para que el futuro ``CreateOpportunityFromLeadUseCase``
tenga de dónde partir] → Marcar lead CONVERTED → Auditar. El lead original
nunca se elimina (§18).

Atomicity: both bounded contexts (customers, crm) write to the same
underlying connection in one transaction — a converted lead with no customer
row (or vice versa) would be a real data-integrity bug, so this bypasses
each UnitOfWork's own commit-on-exit and commits once at the end,
controlling the shared ``connection`` directly. Rolls back both sides
together on any failure.
"""

from __future__ import annotations

import json

from backend.application.crm.authorization import CRMAuthorizationPolicy
from backend.application.crm.permissions import CRMPermissions
from backend.application.crm.result import CRMResult
from backend.application.customers.authorization import CustomerAuthorizationPolicy
from backend.application.customers.permissions import CustomerPermissions
from backend.domain.crm.entities.lead import Lead
from backend.domain.crm.events import CRMEvents
from backend.domain.crm.events import build_event_payload as build_crm_event_payload
from backend.domain.crm.exceptions import CRMDomainError
from backend.domain.customers.entities.customer import Customer
from backend.domain.customers.entities.customer_account import CustomerAccount
from backend.domain.customers.entities.customer_contact import CustomerContactPerson
from backend.domain.customers.enums import CustomerType
from backend.domain.customers.events import CustomerEvents
from backend.domain.customers.events import build_event_payload as build_customer_event_payload
from backend.domain.customers.exceptions import CustomerDomainError
from backend.domain.customers.policies.duplicate_policy import CustomerDuplicatePolicy
from backend.infrastructure.db.repositories.crm.unit_of_work import CRMUnitOfWork
from backend.infrastructure.db.repositories.customers.unit_of_work import CustomerUnitOfWork


class ConvertLeadUseCase:
    def __init__(
        self, crm_authorization: CRMAuthorizationPolicy | None = None,
        customer_authorization: CustomerAuthorizationPolicy | None = None,
    ) -> None:
        self._crm_auth = crm_authorization or CRMAuthorizationPolicy()
        self._customer_auth = customer_authorization or CustomerAuthorizationPolicy()
        self._duplicates = CustomerDuplicatePolicy()

    def execute(
        self, connection, *, actor_user_id: str, lead_id: str, operation_id: str,
        link_to_customer_id: str | None = None, allow_duplicate: bool = False,
    ) -> CRMResult:
        try:
            self._crm_auth.require(actor_user_id, CRMPermissions.LEADS_CONVERT)
            self._customer_auth.require(actor_user_id, CustomerPermissions.CREATE)
        except (CRMDomainError, CustomerDomainError) as exc:
            return CRMResult.fail(str(exc), "PERMISSION_DENIED", operation_id=operation_id)

        crm_uow = CRMUnitOfWork(connection)
        customers_uow = CustomerUnitOfWork(connection)
        try:
            result = self._convert(
                crm_uow, customers_uow, actor_user_id=actor_user_id, lead_id=lead_id,
                operation_id=operation_id, link_to_customer_id=link_to_customer_id,
                allow_duplicate=allow_duplicate)
        except Exception:
            connection.rollback()
            raise
        if result.success:
            connection.commit()
        else:
            connection.rollback()
        return result

    def _convert(
        self, crm_uow: CRMUnitOfWork, customers_uow: CustomerUnitOfWork, *,
        actor_user_id: str, lead_id: str, operation_id: str,
        link_to_customer_id: str | None, allow_duplicate: bool,
    ) -> CRMResult:
        lead = crm_uow.leads.get(lead_id)
        if lead is None:
            return CRMResult.fail("El lead no existe", "NOT_FOUND", operation_id=operation_id)
        if lead.status.value != "QUALIFIED":
            return CRMResult.fail(
                f"Solo se convierte un lead calificado (está {lead.status.value})",
                "VALIDATION", operation_id=operation_id)

        if link_to_customer_id:
            customer = customers_uow.customers.get(link_to_customer_id)
            if customer is None:
                return CRMResult.fail("El cliente indicado no existe", "NOT_FOUND",
                                      operation_id=operation_id)
        else:
            if not allow_duplicate:
                candidate = {"display_name": lead.display_name, "legal_name": lead.company_name,
                             "phone_e164": lead.phone_e164, "email": lead.email}
                matches = self._duplicates.find_matches(
                    candidate, customers_uow.customers.find_duplicate_rows())
                if matches:
                    return CRMResult.fail(
                        "Posible cliente duplicado — seleccione uno con "
                        "link_to_customer_id o confirme con allow_duplicate", "DUPLICATE",
                        operation_id=operation_id,
                        duplicates=[{"customer_id": m.customer_id, "reasons": list(m.reasons)}
                                    for m in matches])
            customer = self._create_customer_from_lead(customers_uow, lead,
                                                        actor_user_id, operation_id)

        account = None
        if lead.company_name and not link_to_customer_id:
            account = CustomerAccount.create(customer.id, industry="")
            customers_uow.accounts.save(account)

        if (lead.contact_name or lead.phone_e164 or lead.email) and not link_to_customer_id:
            contact = CustomerContactPerson.create(
                customer.id, lead.contact_name or lead.display_name,
                customer_account_id=account.id if account else None,
                phone_e164=lead.phone_e164, email=lead.email, is_primary=True)
            customers_uow.contacts.save(contact)

        # Oportunidad opcional (§18): CRM-5 no existe todavía. El evento
        # CRM_LEAD_CONVERTED lleva customer_id para que ese futuro use case
        # tenga de dónde partir sin tener que releer el lead.

        try:
            lead.convert()
        except CRMDomainError as exc:
            return CRMResult.fail(str(exc), "VALIDATION", operation_id=operation_id)
        crm_uow.leads.update(lead)

        crm_uow.audit.record(action=CRMEvents.LEAD_CONVERTED, actor_user_id=actor_user_id,
                             lead_id=lead.id, reason="conversión a cliente",
                             operation_id=operation_id)
        crm_payload = build_crm_event_payload(
            CRMEvents.LEAD_CONVERTED, operation_id=operation_id, lead_id=lead.id,
            user_id=actor_user_id, customer_id=customer.id)
        crm_uow.outbox.enqueue(crm_payload["event_id"], CRMEvents.LEAD_CONVERTED,
                               json.dumps(crm_payload), operation_id)

        if not link_to_customer_id:
            customers_uow.audit.record(action=CustomerEvents.CREATED, actor_user_id=actor_user_id,
                                       customer_id=customer.id, reason=f"conversión de lead {lead.code}",
                                       operation_id=operation_id)
            customer_payload = build_customer_event_payload(
                CustomerEvents.CREATED, operation_id=operation_id, customer_id=customer.id,
                user_id=actor_user_id, source_lead_id=lead.id)
            customers_uow.outbox.enqueue(customer_payload["event_id"], CustomerEvents.CREATED,
                                         json.dumps(customer_payload), operation_id)

        return CRMResult.ok("Lead convertido", entity_id=lead.id, operation_id=operation_id,
                            customer_id=customer.id)

    @staticmethod
    def _create_customer_from_lead(customers_uow: CustomerUnitOfWork, lead: Lead,
                                   actor_user_id: str, operation_id: str) -> Customer:
        customer = Customer.create(
            customers_uow.customers.next_code(), lead.display_name,
            CustomerType.BUSINESS if lead.company_name else CustomerType.INDIVIDUAL,
            legal_name=lead.company_name, source=f"lead:{lead.code}",
            origin_branch_id=lead.origin_branch_id,
            account_owner_user_id=lead.assigned_user_id, territory_id=lead.territory_id,
            created_by_user_id=actor_user_id, operation_id=f"{operation_id}:customer")
        customers_uow.customers.save(customer, operation_id=f"{operation_id}:customer")
        return customer
