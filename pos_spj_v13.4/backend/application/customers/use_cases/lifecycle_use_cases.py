"""Customer Master lifecycle use cases: create, update, activate, deactivate,
suspend, block, close.

Each: validates permission, runs in a CustomerUnitOfWork, records audit and
enqueues the canonical event to the outbox (dispatched post-commit).
Idempotent on create (operation_id). Mirrors
backend/application/suppliers/use_cases/lifecycle_use_cases.py.
"""

from __future__ import annotations

import json

from backend.application.customers.authorization import CustomerAuthorizationPolicy
from backend.application.customers.permissions import CustomerPermissions
from backend.application.customers.result import CustomerResult
from backend.domain.customers.entities.customer import Customer
from backend.domain.customers.enums import CustomerType
from backend.domain.customers.events import CustomerEvents, build_event_payload
from backend.domain.customers.exceptions import CustomerDomainError
from backend.domain.customers.policies.duplicate_policy import CustomerDuplicatePolicy
from backend.infrastructure.db.repositories.customers.unit_of_work import CustomerUnitOfWork


class _BaseUseCase:
    def __init__(self, authorization: CustomerAuthorizationPolicy | None = None) -> None:
        self._auth = authorization or CustomerAuthorizationPolicy()

    def _emit(self, uow, event_name: str, customer_id: str, operation_id: str,
              actor_user_id: str, **extra) -> None:
        payload = build_event_payload(event_name, operation_id=operation_id,
                                      customer_id=customer_id, user_id=actor_user_id, **extra)
        uow.outbox.enqueue(payload["event_id"], event_name, json.dumps(payload), operation_id)


class CreateCustomerUseCase(_BaseUseCase):
    def __init__(self, authorization=None) -> None:
        super().__init__(authorization)
        self._duplicates = CustomerDuplicatePolicy()

    def execute(
        self, connection, *, actor_user_id: str, display_name: str, operation_id: str,
        customer_type: str = CustomerType.INDIVIDUAL.value, legal_name: str = "",
        first_name: str = "", last_name: str = "", second_last_name: str = "",
        commercial_name: str = "", source: str = "", origin_branch_id: str | None = None,
        account_owner_user_id: str | None = None, territory_id: str | None = None,
        tax_identifier: str | None = None, phone_e164: str | None = None,
        email: str | None = None, as_prospect: bool = False,
        allow_duplicate: bool = False,
    ) -> CustomerResult:
        try:
            self._auth.require(actor_user_id, CustomerPermissions.CREATE)
        except CustomerDomainError as exc:
            return CustomerResult.fail(str(exc), "PERMISSION_DENIED", operation_id=operation_id)
        with CustomerUnitOfWork(connection) as uow:
            existing = uow.customers.get_by_operation_id(operation_id)
            if existing is not None:
                return CustomerResult.ok("Cliente ya registrado", entity_id=existing.id,
                                         operation_id=operation_id)
            if not allow_duplicate:
                candidate = {"tax_identifier": tax_identifier, "display_name": display_name,
                             "legal_name": legal_name, "phone_e164": phone_e164, "email": email}
                matches = self._duplicates.find_matches(
                    candidate, uow.customers.find_duplicate_rows())
                if matches:
                    return CustomerResult.fail(
                        "Posible cliente duplicado", "DUPLICATE", operation_id=operation_id,
                        duplicates=[{"customer_id": m.customer_id, "reasons": list(m.reasons)}
                                    for m in matches])
            try:
                customer = Customer.create(
                    uow.customers.next_code(), display_name, CustomerType(customer_type),
                    legal_name=legal_name, first_name=first_name, last_name=last_name,
                    second_last_name=second_last_name, commercial_name=commercial_name,
                    source=source, origin_branch_id=origin_branch_id,
                    account_owner_user_id=account_owner_user_id, territory_id=territory_id,
                    created_by_user_id=actor_user_id, operation_id=operation_id,
                    as_prospect=as_prospect)
            except (CustomerDomainError, ValueError) as exc:
                return CustomerResult.fail(str(exc), "VALIDATION", operation_id=operation_id)
            uow.customers.save(customer, operation_id=operation_id)
            uow.audit.record(action=CustomerEvents.CREATED, actor_user_id=actor_user_id,
                             customer_id=customer.id,
                             after_json=json.dumps({"display_name": display_name}),
                             reason="alta", operation_id=operation_id)
            self._emit(uow, CustomerEvents.CREATED, customer.id, operation_id, actor_user_id)
        return CustomerResult.ok("Cliente creado", entity_id=customer.id,
                                 operation_id=operation_id, code=str(customer.code))


class UpdateCustomerUseCase(_BaseUseCase):
    def execute(
        self, connection, *, actor_user_id: str, customer_id: str, operation_id: str,
        display_name: str | None = None, legal_name: str | None = None,
        commercial_name: str | None = None, source: str | None = None,
    ) -> CustomerResult:
        try:
            self._auth.require(actor_user_id, CustomerPermissions.EDIT)
        except CustomerDomainError as exc:
            return CustomerResult.fail(str(exc), "PERMISSION_DENIED", operation_id=operation_id)
        with CustomerUnitOfWork(connection) as uow:
            customer = uow.customers.get(customer_id)
            if customer is None:
                return CustomerResult.fail("El cliente no existe", "NOT_FOUND",
                                           operation_id=operation_id)
            if display_name is not None:
                if not display_name.strip():
                    return CustomerResult.fail("display_name no puede quedar vacío",
                                               "VALIDATION", operation_id=operation_id)
                customer.display_name = display_name.strip()
            if legal_name is not None:
                customer.legal_name = legal_name.strip()
            if commercial_name is not None:
                customer.commercial_name = commercial_name.strip()
            if source is not None:
                customer.source = source
            customer.record_edit()
            uow.customers.update(customer)
            uow.audit.record(action=CustomerEvents.UPDATED, actor_user_id=actor_user_id,
                             customer_id=customer.id, reason="edición", operation_id=operation_id)
            self._emit(uow, CustomerEvents.UPDATED, customer.id, operation_id, actor_user_id)
        return CustomerResult.ok("Cliente actualizado", entity_id=customer_id,
                                 operation_id=operation_id)


class _TransitionUseCase(_BaseUseCase):
    permission = ""
    event_name = ""

    def _apply(self, customer: Customer, *, actor_user_id: str, reason: str) -> None:
        raise NotImplementedError

    def execute(self, connection, *, actor_user_id: str, customer_id: str,
                operation_id: str, reason: str = "") -> CustomerResult:
        try:
            self._auth.require(actor_user_id, self.permission)
        except CustomerDomainError as exc:
            return CustomerResult.fail(str(exc), "PERMISSION_DENIED", operation_id=operation_id)
        with CustomerUnitOfWork(connection) as uow:
            customer = uow.customers.get(customer_id)
            if customer is None:
                return CustomerResult.fail("El cliente no existe", "NOT_FOUND",
                                           operation_id=operation_id)
            try:
                self._apply(customer, actor_user_id=actor_user_id, reason=reason)
            except CustomerDomainError as exc:
                return CustomerResult.fail(str(exc), "VALIDATION", operation_id=operation_id)
            uow.customers.update(customer)
            uow.audit.record(action=self.event_name, actor_user_id=actor_user_id,
                             customer_id=customer.id, reason=reason, operation_id=operation_id)
            self._emit(uow, self.event_name, customer.id, operation_id, actor_user_id)
        return CustomerResult.ok("Operación registrada", entity_id=customer_id,
                                 operation_id=operation_id)


class ActivateCustomerUseCase(_TransitionUseCase):
    permission = CustomerPermissions.ACTIVATE
    event_name = CustomerEvents.ACTIVATED

    def _apply(self, customer, *, actor_user_id, reason):
        customer.activate()


class DeactivateCustomerUseCase(_TransitionUseCase):
    """Soft-delete: reversible, preserves history — exact functional parity
    with ``ModuloClientes.eliminar_cliente()`` (legacy). See
    backend/domain/customers/entities/customer.py::Customer.deactivate."""

    permission = CustomerPermissions.DEACTIVATE
    event_name = CustomerEvents.DEACTIVATED

    def _apply(self, customer, *, actor_user_id, reason):
        customer.deactivate(reason)


class SuspendCustomerUseCase(_TransitionUseCase):
    permission = CustomerPermissions.SUSPEND
    event_name = CustomerEvents.SUSPENDED

    def _apply(self, customer, *, actor_user_id, reason):
        customer.suspend(reason)


class BlockCustomerUseCase(_TransitionUseCase):
    permission = CustomerPermissions.BLOCK
    event_name = CustomerEvents.BLOCKED

    def _apply(self, customer, *, actor_user_id, reason):
        customer.block(reason)


class CloseCustomerUseCase(_TransitionUseCase):
    permission = CustomerPermissions.CLOSE
    event_name = CustomerEvents.CLOSED

    def _apply(self, customer, *, actor_user_id, reason):
        customer.close(reason)
