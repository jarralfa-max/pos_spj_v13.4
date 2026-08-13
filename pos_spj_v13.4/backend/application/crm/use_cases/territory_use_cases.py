"""SalesTerritory use cases: create, deactivate, and assign a territory to
a customer (§33-36).

AssignCustomerTerritoryUseCase is the one place this file touches the
Customers bounded context — it keeps ``Customer.territory_id`` (CRM-3's
denormalized fast-path field) in sync, same atomic-shared-connection
pattern as ConvertLeadUseCase/AnonymizeCustomerUseCase. No SoD reason is
required for territory reassignment: §73's list singles out "reasignar
cartera/propietario", not territorio, so TERRITORIES_MANAGE alone gates it.
"""

from __future__ import annotations

import json

from backend.application.crm.authorization import CRMAuthorizationPolicy
from backend.application.crm.permissions import CRMPermissions
from backend.application.crm.result import CRMResult
from backend.domain.crm.entities.sales_territory import SalesTerritory
from backend.domain.crm.events import CRMEvents, build_event_payload
from backend.domain.crm.exceptions import CRMDomainError
from backend.infrastructure.db.repositories.crm.unit_of_work import CRMUnitOfWork
from backend.infrastructure.db.repositories.customers.unit_of_work import CustomerUnitOfWork


class _BaseUseCase:
    def __init__(self, authorization: CRMAuthorizationPolicy | None = None) -> None:
        self._auth = authorization or CRMAuthorizationPolicy()


class CreateSalesTerritoryUseCase(_BaseUseCase):
    def execute(self, connection, *, actor_user_id: str, code: str, name: str,
                operation_id: str, description: str = "") -> CRMResult:
        try:
            self._auth.require(actor_user_id, CRMPermissions.TERRITORIES_MANAGE)
        except CRMDomainError as exc:
            return CRMResult.fail(str(exc), "PERMISSION_DENIED", operation_id=operation_id)
        with CRMUnitOfWork(connection) as uow:
            if uow.territories.get_by_code(code):
                return CRMResult.fail("Ya existe un territorio con ese código", "DUPLICATE",
                                      operation_id=operation_id)
            try:
                territory = SalesTerritory.create(code, name, description=description)
            except CRMDomainError as exc:
                return CRMResult.fail(str(exc), "VALIDATION", operation_id=operation_id)
            uow.territories.save(territory)
            uow.audit.record(action=CRMEvents.TERRITORY_CREATED, actor_user_id=actor_user_id,
                             operation_id=operation_id,
                             after_json=json.dumps({"territory_id": territory.id,
                                                    "code": territory.code}))
            payload = build_event_payload(CRMEvents.TERRITORY_CREATED, operation_id=operation_id,
                                          user_id=actor_user_id, territory_id=territory.id)
            uow.outbox.enqueue(payload["event_id"], CRMEvents.TERRITORY_CREATED,
                               json.dumps(payload), operation_id)
            return CRMResult.ok("Territorio creado", entity_id=territory.id,
                                operation_id=operation_id)


class DeactivateSalesTerritoryUseCase(_BaseUseCase):
    def execute(self, connection, *, actor_user_id: str, territory_id: str,
                operation_id: str) -> CRMResult:
        try:
            self._auth.require(actor_user_id, CRMPermissions.TERRITORIES_MANAGE)
        except CRMDomainError as exc:
            return CRMResult.fail(str(exc), "PERMISSION_DENIED", operation_id=operation_id)
        with CRMUnitOfWork(connection) as uow:
            territory = uow.territories.get(territory_id)
            if territory is None:
                return CRMResult.fail("El territorio no existe", "NOT_FOUND",
                                      operation_id=operation_id)
            territory.deactivate()
            uow.territories.update(territory)
            uow.audit.record(action=CRMEvents.TERRITORY_DEACTIVATED, actor_user_id=actor_user_id,
                             operation_id=operation_id,
                             after_json=json.dumps({"territory_id": territory.id}))
            payload = build_event_payload(CRMEvents.TERRITORY_DEACTIVATED,
                                          operation_id=operation_id, user_id=actor_user_id,
                                          territory_id=territory.id)
            uow.outbox.enqueue(payload["event_id"], CRMEvents.TERRITORY_DEACTIVATED,
                               json.dumps(payload), operation_id)
            return CRMResult.ok("Territorio desactivado", entity_id=territory.id,
                                operation_id=operation_id)


class AssignCustomerTerritoryUseCase(_BaseUseCase):
    def execute(self, connection, *, actor_user_id: str, customer_id: str,
                territory_id: str | None, operation_id: str) -> CRMResult:
        try:
            self._auth.require(actor_user_id, CRMPermissions.TERRITORIES_MANAGE)
        except CRMDomainError as exc:
            return CRMResult.fail(str(exc), "PERMISSION_DENIED", operation_id=operation_id)

        crm_uow = CRMUnitOfWork(connection)
        customers_uow = CustomerUnitOfWork(connection)
        try:
            result = self._assign(crm_uow, customers_uow, actor_user_id=actor_user_id,
                                  customer_id=customer_id, territory_id=territory_id,
                                  operation_id=operation_id)
        except Exception:
            connection.rollback()
            raise
        if result.success:
            connection.commit()
        else:
            connection.rollback()
        return result

    def _assign(self, crm_uow: CRMUnitOfWork, customers_uow: CustomerUnitOfWork, *,
                actor_user_id: str, customer_id: str, territory_id: str | None,
                operation_id: str) -> CRMResult:
        if territory_id:
            territory = crm_uow.territories.get(territory_id)
            if territory is None:
                return CRMResult.fail("El territorio no existe", "NOT_FOUND",
                                      operation_id=operation_id)
            if not territory.active:
                return CRMResult.fail("El territorio está inactivo", "VALIDATION",
                                      operation_id=operation_id)

        customer = customers_uow.customers.get(customer_id)
        if customer is None:
            return CRMResult.fail("El cliente no existe", "NOT_FOUND", operation_id=operation_id)

        customer.assign_territory(territory_id)
        customers_uow.customers.update(customer)

        crm_uow.audit.record(action=CRMEvents.CUSTOMER_TERRITORY_ASSIGNED,
                             actor_user_id=actor_user_id, operation_id=operation_id,
                             after_json=json.dumps({"customer_id": customer_id,
                                                    "territory_id": territory_id}))
        payload = build_event_payload(CRMEvents.CUSTOMER_TERRITORY_ASSIGNED,
                                      operation_id=operation_id, user_id=actor_user_id,
                                      customer_id=customer_id, territory_id=territory_id)
        crm_uow.outbox.enqueue(payload["event_id"], CRMEvents.CUSTOMER_TERRITORY_ASSIGNED,
                               json.dumps(payload), operation_id)
        return CRMResult.ok("Territorio asignado", entity_id=customer_id,
                            operation_id=operation_id)
