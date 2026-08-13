"""CustomerOwnership use case: assign/reassign a customer's owner for a
given OwnershipType (§33-36: "con historial de asignación — no solo
vendedor_id plano").

Requires CUSTOMER_OWNER_ASSIGN for the first assignment of a given
(customer, ownership_type) pair and CUSTOMER_OWNER_REASSIGN when one already
exists — same assign/reassign permission split CRM-5/CRM-6 established for
Opportunities/Tasks (AssignCRMTaskUseCase). Reassignment additionally
requires a justification via
CustomerSegregationOfDutiesPolicy.enforce_ownership_reassignment_justified
(§73: "reasignar cartera/propietario requiere un motivo").

Only OwnershipType.PRIMARY touches the Customers bounded context: it keeps
Customer.account_owner_user_id (CRM-3's denormalized fast-path field,
consumed by CustomerDataScopeResolver for OWN-scope resolution) in sync,
via the same atomic-shared-connection pattern as
ConvertLeadUseCase/AnonymizeCustomerUseCase. The other ownership types
(SECONDARY/ACCOUNT_MANAGER/CREDIT_MANAGER/SERVICE_OWNER) are informational
roles Customer has no column for, so they stay CRM-only.
"""

from __future__ import annotations

import json

from backend.application.crm.authorization import CRMAuthorizationPolicy
from backend.application.crm.permissions import CRMPermissions
from backend.application.crm.result import CRMResult
from backend.domain.crm.entities.customer_ownership import CustomerOwnership
from backend.domain.crm.enums import OwnershipType
from backend.domain.crm.events import CRMEvents, build_event_payload
from backend.domain.crm.exceptions import CRMDomainError
from backend.domain.customers.exceptions import CustomerSegregationOfDutiesError
from backend.domain.customers.policies.segregation_of_duties_policy import (
    CustomerSegregationOfDutiesPolicy,
)
from backend.infrastructure.db.repositories.crm.unit_of_work import CRMUnitOfWork
from backend.infrastructure.db.repositories.customers.unit_of_work import CustomerUnitOfWork


class AssignCustomerOwnerUseCase:
    def __init__(self, crm_authorization: CRMAuthorizationPolicy | None = None) -> None:
        self._auth = crm_authorization or CRMAuthorizationPolicy()
        self._sod = CustomerSegregationOfDutiesPolicy()

    def execute(
        self, connection, *, actor_user_id: str, customer_id: str, ownership_type: str,
        owner_user_id: str, operation_id: str, reason: str = "",
    ) -> CRMResult:
        try:
            ownership_type_enum = OwnershipType(ownership_type)
        except ValueError:
            return CRMResult.fail(f"Tipo de propietario inválido: {ownership_type}",
                                  "VALIDATION", operation_id=operation_id)

        crm_uow = CRMUnitOfWork(connection)
        customers_uow = CustomerUnitOfWork(connection)
        try:
            result = self._assign(
                crm_uow, customers_uow, actor_user_id=actor_user_id, customer_id=customer_id,
                ownership_type=ownership_type_enum, owner_user_id=owner_user_id,
                operation_id=operation_id, reason=reason)
        except Exception:
            connection.rollback()
            raise
        if result.success:
            connection.commit()
        else:
            connection.rollback()
        return result

    def _assign(
        self, crm_uow: CRMUnitOfWork, customers_uow: CustomerUnitOfWork, *,
        actor_user_id: str, customer_id: str, ownership_type: OwnershipType,
        owner_user_id: str, operation_id: str, reason: str,
    ) -> CRMResult:
        existing = crm_uow.ownerships.get_latest(customer_id, ownership_type.value)
        permission = (CRMPermissions.CUSTOMER_OWNER_REASSIGN if existing
                     else CRMPermissions.CUSTOMER_OWNER_ASSIGN)
        try:
            self._auth.require(actor_user_id, permission)
        except CRMDomainError as exc:
            return CRMResult.fail(str(exc), "PERMISSION_DENIED", operation_id=operation_id)

        if existing is not None:
            try:
                self._sod.enforce_ownership_reassignment_justified(reason)
            except CustomerSegregationOfDutiesError as exc:
                return CRMResult.fail(str(exc), "SOD_VIOLATION", operation_id=operation_id)

        if ownership_type is OwnershipType.PRIMARY:
            customer = customers_uow.customers.get(customer_id)
            if customer is None:
                return CRMResult.fail("El cliente no existe", "NOT_FOUND",
                                      operation_id=operation_id)

        try:
            ownership = CustomerOwnership.capture(
                customer_id, ownership_type, owner_user_id, assigned_by_user_id=actor_user_id,
                reason=reason, operation_id=operation_id)
        except CRMDomainError as exc:
            return CRMResult.fail(str(exc), "VALIDATION", operation_id=operation_id)
        crm_uow.ownerships.save(ownership, operation_id=operation_id)

        if ownership_type is OwnershipType.PRIMARY:
            customer.assign_owner(owner_user_id)
            customers_uow.customers.update(customer)

        event_name = (CRMEvents.CUSTOMER_OWNER_REASSIGNED if existing
                     else CRMEvents.CUSTOMER_OWNER_ASSIGNED)
        crm_uow.audit.record(
            action=event_name, actor_user_id=actor_user_id, reason=reason,
            operation_id=operation_id,
            before_json=json.dumps({"ownership_type": ownership_type.value,
                                    "previous_owner_user_id":
                                        existing.owner_user_id if existing else None}),
            after_json=json.dumps({"customer_id": customer_id, "owner_user_id": owner_user_id}))
        payload = build_event_payload(
            event_name, operation_id=operation_id, user_id=actor_user_id,
            customer_id=customer_id, ownership_type=ownership_type.value,
            owner_user_id=owner_user_id)
        crm_uow.outbox.enqueue(payload["event_id"], event_name, json.dumps(payload),
                               operation_id)

        message = "Propietario reasignado" if existing else "Propietario asignado"
        return CRMResult.ok(message, entity_id=ownership.id, operation_id=operation_id)
