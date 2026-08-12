"""Customer contact use cases (§13, §58): add, update, set primary, remove.

Same shape as backend/application/customers/use_cases/lifecycle_use_cases.py
(permission gate → CustomerUnitOfWork → audit → outbox event), scoped to the
``CustomerContactPerson`` child entity.
"""

from __future__ import annotations

import json

from backend.application.customers.authorization import CustomerAuthorizationPolicy
from backend.application.customers.permissions import CustomerPermissions
from backend.application.customers.result import CustomerResult
from backend.domain.customers.entities.customer_contact import CustomerContactPerson
from backend.domain.customers.enums import ContactDecisionRole
from backend.domain.customers.events import CustomerEvents, build_event_payload
from backend.domain.customers.exceptions import CustomerDomainError
from backend.infrastructure.db.repositories.customers.unit_of_work import CustomerUnitOfWork


class _BaseContactUseCase:
    def __init__(self, authorization: CustomerAuthorizationPolicy | None = None) -> None:
        self._auth = authorization or CustomerAuthorizationPolicy()

    def _emit(self, uow, event_name: str, customer_id: str, operation_id: str,
              actor_user_id: str, **extra) -> None:
        payload = build_event_payload(event_name, operation_id=operation_id,
                                      customer_id=customer_id, user_id=actor_user_id, **extra)
        uow.outbox.enqueue(payload["event_id"], event_name, json.dumps(payload), operation_id)


class AddCustomerContactUseCase(_BaseContactUseCase):
    def execute(
        self, connection, *, actor_user_id: str, customer_id: str, first_name: str,
        operation_id: str, last_name: str = "", customer_account_id: str | None = None,
        job_title: str = "", department: str = "", phone_e164: str | None = None,
        email: str | None = None, decision_role: str = ContactDecisionRole.OTHER.value,
        is_primary: bool = False,
    ) -> CustomerResult:
        try:
            self._auth.require(actor_user_id, CustomerPermissions.CONTACT_CREATE)
        except CustomerDomainError as exc:
            return CustomerResult.fail(str(exc), "PERMISSION_DENIED", operation_id=operation_id)
        with CustomerUnitOfWork(connection) as uow:
            if uow.customers.get(customer_id) is None:
                return CustomerResult.fail("El cliente no existe", "NOT_FOUND",
                                           operation_id=operation_id)
            try:
                contact = CustomerContactPerson.create(
                    customer_id, first_name, last_name=last_name,
                    customer_account_id=customer_account_id, job_title=job_title,
                    department=department, phone_e164=phone_e164, email=email,
                    decision_role=ContactDecisionRole(decision_role), is_primary=is_primary)
            except (CustomerDomainError, ValueError) as exc:
                return CustomerResult.fail(str(exc), "VALIDATION", operation_id=operation_id)
            if is_primary:
                uow.contacts.clear_primary(customer_id)
            uow.contacts.save(contact)
            uow.audit.record(action=CustomerEvents.CONTACT_ADDED, actor_user_id=actor_user_id,
                             customer_id=customer_id, reason="alta de contacto",
                             operation_id=operation_id)
            self._emit(uow, CustomerEvents.CONTACT_ADDED, customer_id, operation_id,
                       actor_user_id, contact_id=contact.id)
        return CustomerResult.ok("Contacto agregado", entity_id=contact.id,
                                 operation_id=operation_id)


class UpdateCustomerContactUseCase(_BaseContactUseCase):
    def execute(
        self, connection, *, actor_user_id: str, contact_id: str, operation_id: str,
        first_name: str | None = None, last_name: str | None = None,
        job_title: str | None = None, department: str | None = None,
        phone_e164: str | None = None, email: str | None = None,
        decision_role: str | None = None,
    ) -> CustomerResult:
        try:
            self._auth.require(actor_user_id, CustomerPermissions.CONTACT_EDIT)
        except CustomerDomainError as exc:
            return CustomerResult.fail(str(exc), "PERMISSION_DENIED", operation_id=operation_id)
        with CustomerUnitOfWork(connection) as uow:
            contact = uow.contacts.get(contact_id)
            if contact is None:
                return CustomerResult.fail("El contacto no existe", "NOT_FOUND",
                                           operation_id=operation_id)
            if first_name is not None:
                contact.first_name = first_name.strip()
            if last_name is not None:
                contact.last_name = last_name.strip()
            if job_title is not None:
                contact.job_title = job_title
            if department is not None:
                contact.department = department
            if phone_e164 is not None:
                contact.phone_e164 = phone_e164
            if email is not None:
                contact.email = email
            if decision_role is not None:
                contact.decision_role = ContactDecisionRole(decision_role)
            uow.contacts.update(contact)
            uow.audit.record(action=CustomerEvents.CONTACT_UPDATED, actor_user_id=actor_user_id,
                             customer_id=contact.customer_id, reason="edición de contacto",
                             operation_id=operation_id)
            self._emit(uow, CustomerEvents.CONTACT_UPDATED, contact.customer_id, operation_id,
                       actor_user_id, contact_id=contact.id)
        return CustomerResult.ok("Contacto actualizado", entity_id=contact_id,
                                 operation_id=operation_id)


class SetPrimaryCustomerContactUseCase(_BaseContactUseCase):
    def execute(self, connection, *, actor_user_id: str, contact_id: str,
                operation_id: str) -> CustomerResult:
        try:
            self._auth.require(actor_user_id, CustomerPermissions.CONTACT_SET_PRIMARY)
        except CustomerDomainError as exc:
            return CustomerResult.fail(str(exc), "PERMISSION_DENIED", operation_id=operation_id)
        with CustomerUnitOfWork(connection) as uow:
            contact = uow.contacts.get(contact_id)
            if contact is None:
                return CustomerResult.fail("El contacto no existe", "NOT_FOUND",
                                           operation_id=operation_id)
            uow.contacts.clear_primary(contact.customer_id)
            contact.is_primary = True
            uow.contacts.update(contact)
            uow.audit.record(action=CustomerEvents.CONTACT_UPDATED, actor_user_id=actor_user_id,
                             customer_id=contact.customer_id,
                             reason="marcado como contacto principal", operation_id=operation_id)
            self._emit(uow, CustomerEvents.CONTACT_UPDATED, contact.customer_id, operation_id,
                       actor_user_id, contact_id=contact.id, set_primary=True)
        return CustomerResult.ok("Contacto marcado como principal", entity_id=contact_id,
                                 operation_id=operation_id)


class RemoveCustomerContactUseCase(_BaseContactUseCase):
    def execute(self, connection, *, actor_user_id: str, contact_id: str,
                operation_id: str) -> CustomerResult:
        try:
            self._auth.require(actor_user_id, CustomerPermissions.CONTACT_DELETE)
        except CustomerDomainError as exc:
            return CustomerResult.fail(str(exc), "PERMISSION_DENIED", operation_id=operation_id)
        with CustomerUnitOfWork(connection) as uow:
            contact = uow.contacts.get(contact_id)
            if contact is None:
                return CustomerResult.fail("El contacto no existe", "NOT_FOUND",
                                           operation_id=operation_id)
            uow.contacts.remove(contact_id)
            uow.audit.record(action=CustomerEvents.CONTACT_REMOVED, actor_user_id=actor_user_id,
                             customer_id=contact.customer_id, reason="eliminación de contacto",
                             operation_id=operation_id)
            self._emit(uow, CustomerEvents.CONTACT_REMOVED, contact.customer_id, operation_id,
                       actor_user_id, contact_id=contact_id)
        return CustomerResult.ok("Contacto eliminado", entity_id=contact_id,
                                 operation_id=operation_id)
