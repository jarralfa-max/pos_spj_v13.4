"""Customer address use cases (§14, §58): add, update, set default, remove.

Same shape as contact_use_cases.py, scoped to the ``CustomerAddress`` child
entity.
"""

from __future__ import annotations

import json

from backend.application.customers.authorization import CustomerAuthorizationPolicy
from backend.application.customers.permissions import CustomerPermissions
from backend.application.customers.result import CustomerResult
from backend.domain.customers.entities.customer_address import CustomerAddress
from backend.domain.customers.enums import AddressType
from backend.domain.customers.events import CustomerEvents, build_event_payload
from backend.domain.customers.exceptions import CustomerDomainError
from backend.infrastructure.db.repositories.customers.unit_of_work import CustomerUnitOfWork


class _BaseAddressUseCase:
    def __init__(self, authorization: CustomerAuthorizationPolicy | None = None) -> None:
        self._auth = authorization or CustomerAuthorizationPolicy()

    def _emit(self, uow, event_name: str, customer_id: str, operation_id: str,
              actor_user_id: str, **extra) -> None:
        payload = build_event_payload(event_name, operation_id=operation_id,
                                      customer_id=customer_id, user_id=actor_user_id, **extra)
        uow.outbox.enqueue(payload["event_id"], event_name, json.dumps(payload), operation_id)


class AddCustomerAddressUseCase(_BaseAddressUseCase):
    def execute(
        self, connection, *, actor_user_id: str, customer_id: str, street: str,
        operation_id: str, address_type: str = AddressType.DELIVERY.value,
        external_number: str = "", internal_number: str = "", neighborhood: str = "",
        postal_code: str = "", locality: str = "", municipality: str = "", state: str = "",
        country: str = "MX", references: str = "", latitude: float | None = None,
        longitude: float | None = None, is_default: bool = False,
    ) -> CustomerResult:
        try:
            self._auth.require(actor_user_id, CustomerPermissions.ADDRESS_CREATE)
        except CustomerDomainError as exc:
            return CustomerResult.fail(str(exc), "PERMISSION_DENIED", operation_id=operation_id)
        with CustomerUnitOfWork(connection) as uow:
            if uow.customers.get(customer_id) is None:
                return CustomerResult.fail("El cliente no existe", "NOT_FOUND",
                                           operation_id=operation_id)
            try:
                address = CustomerAddress.create(
                    customer_id, AddressType(address_type), street,
                    external_number=external_number, internal_number=internal_number,
                    neighborhood=neighborhood, postal_code=postal_code, locality=locality,
                    municipality=municipality, state=state, country=country,
                    references=references, latitude=latitude, longitude=longitude,
                    is_default=is_default)
            except (CustomerDomainError, ValueError) as exc:
                return CustomerResult.fail(str(exc), "VALIDATION", operation_id=operation_id)
            if is_default:
                uow.addresses.clear_default(customer_id, address_type)
            uow.addresses.save(address)
            uow.audit.record(action=CustomerEvents.ADDRESS_ADDED, actor_user_id=actor_user_id,
                             customer_id=customer_id, reason="alta de dirección",
                             operation_id=operation_id)
            self._emit(uow, CustomerEvents.ADDRESS_ADDED, customer_id, operation_id,
                       actor_user_id, address_id=address.id)
        return CustomerResult.ok("Dirección agregada", entity_id=address.id,
                                 operation_id=operation_id)


class UpdateCustomerAddressUseCase(_BaseAddressUseCase):
    def execute(
        self, connection, *, actor_user_id: str, address_id: str, operation_id: str,
        street: str | None = None, external_number: str | None = None,
        internal_number: str | None = None, neighborhood: str | None = None,
        postal_code: str | None = None, locality: str | None = None,
        municipality: str | None = None, state: str | None = None,
        country: str | None = None, references: str | None = None,
        latitude: float | None = None, longitude: float | None = None,
    ) -> CustomerResult:
        try:
            self._auth.require(actor_user_id, CustomerPermissions.ADDRESS_EDIT)
        except CustomerDomainError as exc:
            return CustomerResult.fail(str(exc), "PERMISSION_DENIED", operation_id=operation_id)
        with CustomerUnitOfWork(connection) as uow:
            address = uow.addresses.get(address_id)
            if address is None:
                return CustomerResult.fail("La dirección no existe", "NOT_FOUND",
                                           operation_id=operation_id)
            for field_name, value in (
                ("street", street), ("external_number", external_number),
                ("internal_number", internal_number), ("neighborhood", neighborhood),
                ("postal_code", postal_code), ("locality", locality),
                ("municipality", municipality), ("state", state), ("country", country),
                ("references", references), ("latitude", latitude), ("longitude", longitude),
            ):
                if value is not None:
                    setattr(address, field_name, value)
            uow.addresses.update(address)
            uow.audit.record(action=CustomerEvents.ADDRESS_UPDATED, actor_user_id=actor_user_id,
                             customer_id=address.customer_id, reason="edición de dirección",
                             operation_id=operation_id)
            self._emit(uow, CustomerEvents.ADDRESS_UPDATED, address.customer_id, operation_id,
                       actor_user_id, address_id=address.id)
        return CustomerResult.ok("Dirección actualizada", entity_id=address_id,
                                 operation_id=operation_id)


class SetDefaultCustomerAddressUseCase(_BaseAddressUseCase):
    def execute(self, connection, *, actor_user_id: str, address_id: str,
                operation_id: str) -> CustomerResult:
        try:
            self._auth.require(actor_user_id, CustomerPermissions.ADDRESS_SET_DEFAULT)
        except CustomerDomainError as exc:
            return CustomerResult.fail(str(exc), "PERMISSION_DENIED", operation_id=operation_id)
        with CustomerUnitOfWork(connection) as uow:
            address = uow.addresses.get(address_id)
            if address is None:
                return CustomerResult.fail("La dirección no existe", "NOT_FOUND",
                                           operation_id=operation_id)
            uow.addresses.clear_default(address.customer_id, address.address_type.value)
            address.is_default = True
            uow.addresses.update(address)
            uow.audit.record(action=CustomerEvents.ADDRESS_UPDATED, actor_user_id=actor_user_id,
                             customer_id=address.customer_id,
                             reason="marcada como predeterminada", operation_id=operation_id)
            self._emit(uow, CustomerEvents.ADDRESS_UPDATED, address.customer_id, operation_id,
                       actor_user_id, address_id=address.id, set_default=True)
        return CustomerResult.ok("Dirección marcada como predeterminada", entity_id=address_id,
                                 operation_id=operation_id)


class RemoveCustomerAddressUseCase(_BaseAddressUseCase):
    def execute(self, connection, *, actor_user_id: str, address_id: str,
                operation_id: str) -> CustomerResult:
        try:
            self._auth.require(actor_user_id, CustomerPermissions.ADDRESS_DELETE)
        except CustomerDomainError as exc:
            return CustomerResult.fail(str(exc), "PERMISSION_DENIED", operation_id=operation_id)
        with CustomerUnitOfWork(connection) as uow:
            address = uow.addresses.get(address_id)
            if address is None:
                return CustomerResult.fail("La dirección no existe", "NOT_FOUND",
                                           operation_id=operation_id)
            uow.addresses.remove(address_id)
            uow.audit.record(action=CustomerEvents.ADDRESS_REMOVED, actor_user_id=actor_user_id,
                             customer_id=address.customer_id, reason="eliminación de dirección",
                             operation_id=operation_id)
            self._emit(uow, CustomerEvents.ADDRESS_REMOVED, address.customer_id, operation_id,
                       actor_user_id, address_id=address_id)
        return CustomerResult.ok("Dirección eliminada", entity_id=address_id,
                                 operation_id=operation_id)
