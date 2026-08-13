"""Customer merge use cases: propose, execute, reject (§45, §73-74).

ProposeCustomerMergeUseCase requires a CONFIRMED_DUPLICATE candidate (when
one is supplied) — merges don't have to originate from the duplicate
workflow (a supervisor can propose one directly), but if a
``duplicate_candidate_id`` is given it must actually be confirmed and must
actually involve both customers, so the candidate record and the merge
stay consistent.

ExecuteCustomerMergeUseCase is the hot-authorized step (§74: "fusión de
clientes" is explicitly one of the operations requiring a second pair of
eyes) — first real consumer of BOTH
``CustomerAuthorizationPolicy.authorize_exception()`` for the second-
authorizer requirement AND
``CustomerSegregationOfDutiesPolicy.enforce_merge_proposer_not_self_
approving()`` for the domain-specific rejection message (the grant's own
``authorized_by != requested_by`` invariant already enforces the same
distinctness structurally — this is intentional belt-and-suspenders,
consuming the exact CRM-2-built method for merge rather than relying only
on the generic grant message).

Data resolution touches only ``customers``' own child tables (contacts,
addresses, accounts, tax profile) — never customer_privacy/customer_credit/
crm tables directly (§45: "notifica bounded contexts... nunca modifica
tablas externas directamente"). Those bounded contexts are expected to
react to CUSTOMER_MERGE_EXECUTED on their own, in future work.
"""

from __future__ import annotations

import json

from backend.application.customers.authorization import CustomerAuthorizationPolicy
from backend.application.customers.permissions import CustomerPermissions
from backend.application.customers.result import CustomerResult
from backend.domain.customers.entities.customer_merge_record import CustomerMergeRecord
from backend.domain.customers.enums import DuplicateCandidateStatus
from backend.domain.customers.events import CustomerEvents, build_event_payload
from backend.domain.customers.exceptions import CustomerDomainError, CustomerSegregationOfDutiesError
from backend.domain.customers.policies.segregation_of_duties_policy import (
    CustomerSegregationOfDutiesPolicy,
)
from backend.infrastructure.db.repositories.customers.unit_of_work import CustomerUnitOfWork


class _BaseUseCase:
    def __init__(self, authorization: CustomerAuthorizationPolicy | None = None) -> None:
        self._auth = authorization or CustomerAuthorizationPolicy()

    def _emit(self, uow, event_name: str, customer_id: str, operation_id: str,
              actor_user_id: str, **extra) -> None:
        payload = build_event_payload(event_name, operation_id=operation_id,
                                      customer_id=customer_id, user_id=actor_user_id, **extra)
        uow.outbox.enqueue(payload["event_id"], event_name, json.dumps(payload), operation_id)


class ProposeCustomerMergeUseCase(_BaseUseCase):
    def execute(
        self, connection, *, actor_user_id: str, master_customer_id: str,
        merged_customer_id: str, operation_id: str, duplicate_candidate_id: str | None = None,
        reason: str = "",
    ) -> CustomerResult:
        try:
            self._auth.require(actor_user_id, CustomerPermissions.DUPLICATES_MERGE)
        except CustomerDomainError as exc:
            return CustomerResult.fail(str(exc), "PERMISSION_DENIED", operation_id=operation_id)
        with CustomerUnitOfWork(connection) as uow:
            master = uow.customers.get(master_customer_id)
            merged = uow.customers.get(merged_customer_id)
            if master is None or merged is None:
                return CustomerResult.fail("Uno de los clientes no existe", "NOT_FOUND",
                                           operation_id=operation_id)
            if master.is_terminal() or merged.is_terminal():
                return CustomerResult.fail(
                    "Uno de los clientes ya no está activo para fusión", "VALIDATION",
                    operation_id=operation_id)
            candidate = None
            if duplicate_candidate_id:
                candidate = uow.duplicate_candidates.get(duplicate_candidate_id)
                if candidate is None:
                    return CustomerResult.fail("El candidato de duplicado no existe",
                                               "NOT_FOUND", operation_id=operation_id)
                if candidate.status is not DuplicateCandidateStatus.CONFIRMED_DUPLICATE:
                    return CustomerResult.fail(
                        "El candidato debe estar confirmado como duplicado antes de fusionar",
                        "VALIDATION", operation_id=operation_id)
                if not (candidate.involves(master_customer_id)
                       and candidate.involves(merged_customer_id)):
                    return CustomerResult.fail(
                        "El candidato de duplicado no corresponde a estos clientes",
                        "VALIDATION", operation_id=operation_id)
            try:
                record = CustomerMergeRecord.propose(
                    master_customer_id, merged_customer_id, actor_user_id,
                    duplicate_candidate_id=duplicate_candidate_id, reason=reason,
                    operation_id=operation_id)
            except CustomerDomainError as exc:
                return CustomerResult.fail(str(exc), "VALIDATION", operation_id=operation_id)
            uow.merge_records.save(record, operation_id=operation_id)
            uow.audit.record(action=CustomerEvents.MERGE_PROPOSED, actor_user_id=actor_user_id,
                             customer_id=master_customer_id, reason=reason,
                             operation_id=operation_id,
                             after_json=json.dumps({"merge_record_id": record.id,
                                                    "merged_customer_id": merged_customer_id}))
            self._emit(uow, CustomerEvents.MERGE_PROPOSED, master_customer_id, operation_id,
                      actor_user_id, merge_record_id=record.id,
                      merged_customer_id=merged_customer_id)
        return CustomerResult.ok("Fusión propuesta", entity_id=record.id,
                                 operation_id=operation_id)


class ExecuteCustomerMergeUseCase(_BaseUseCase):
    def __init__(self, authorization: CustomerAuthorizationPolicy | None = None) -> None:
        super().__init__(authorization)
        self._sod = CustomerSegregationOfDutiesPolicy()

    def execute(self, connection, *, actor_user_id: str, merge_record_id: str,
                operation_id: str, reason: str) -> CustomerResult:
        with CustomerUnitOfWork(connection) as uow:
            record = uow.merge_records.get(merge_record_id)
            if record is None:
                return CustomerResult.fail("La fusión propuesta no existe", "NOT_FOUND",
                                           operation_id=operation_id)
            if record.status.value != "PROPOSED":
                return CustomerResult.fail(
                    f"No se puede ejecutar desde {record.status.value}", "VALIDATION",
                    operation_id=operation_id)
            master = uow.customers.get(record.master_customer_id)
            merged = uow.customers.get(record.merged_customer_id)
            if master is None or merged is None:
                return CustomerResult.fail("Uno de los clientes no existe", "NOT_FOUND",
                                           operation_id=operation_id)
            if master.is_terminal() or merged.is_terminal():
                return CustomerResult.fail(
                    "Uno de los clientes ya no está activo para fusión", "VALIDATION",
                    operation_id=operation_id)

            try:
                self._auth.authorize_exception(
                    authorizer_user_id=actor_user_id, requested_by=record.proposed_by_user_id,
                    permission_code=CustomerPermissions.DUPLICATES_MERGE,
                    operation_id=operation_id, reason=reason)
            except CustomerDomainError as exc:
                return CustomerResult.fail(str(exc), "PERMISSION_DENIED",
                                           operation_id=operation_id)
            try:
                self._sod.enforce_merge_proposer_not_self_approving(
                    record.proposed_by_user_id, actor_user_id)
            except CustomerSegregationOfDutiesError as exc:
                return CustomerResult.fail(str(exc), "SOD_VIOLATION", operation_id=operation_id)

            uow.contacts.reassign_customer_id(merged.id, master.id)
            uow.addresses.reassign_customer_id(merged.id, master.id)
            uow.accounts.reassign_customer_id(merged.id, master.id)
            if uow.tax_profiles.get_for_customer(master.id) is None:
                uow.tax_profiles.reassign_customer_id(merged.id, master.id)
            else:
                uow.tax_profiles.delete_for_customer(merged.id)

            merged.mark_merged(master.id)
            uow.customers.update(merged)

            if record.duplicate_candidate_id:
                candidate = uow.duplicate_candidates.get(record.duplicate_candidate_id)
                if candidate is not None:
                    candidate.mark_merged()
                    uow.duplicate_candidates.update(candidate)

            record.execute(actor_user_id)
            uow.merge_records.update(record)

            uow.audit.record(
                action=CustomerEvents.MERGE_EXECUTED, actor_user_id=actor_user_id,
                customer_id=master.id, reason=reason, operation_id=operation_id,
                before_json=json.dumps({"merged_customer_id": merged.id}),
                after_json=json.dumps({"master_customer_id": master.id,
                                       "merge_record_id": record.id}))
            self._emit(uow, CustomerEvents.MERGE_EXECUTED, master.id, operation_id,
                      actor_user_id, merged_customer_id=merged.id, master_customer_id=master.id)
        return CustomerResult.ok("Fusión ejecutada", entity_id=record.id,
                                 operation_id=operation_id, master_customer_id=master.id,
                                 merged_customer_id=merged.id)


class RejectCustomerMergeUseCase(_BaseUseCase):
    def execute(self, connection, *, actor_user_id: str, merge_record_id: str, reason: str,
                operation_id: str) -> CustomerResult:
        try:
            self._auth.require(actor_user_id, CustomerPermissions.DUPLICATES_MERGE)
        except CustomerDomainError as exc:
            return CustomerResult.fail(str(exc), "PERMISSION_DENIED", operation_id=operation_id)
        with CustomerUnitOfWork(connection) as uow:
            record = uow.merge_records.get(merge_record_id)
            if record is None:
                return CustomerResult.fail("La fusión propuesta no existe", "NOT_FOUND",
                                           operation_id=operation_id)
            try:
                record.reject(actor_user_id, reason)
            except CustomerDomainError as exc:
                return CustomerResult.fail(str(exc), "VALIDATION", operation_id=operation_id)
            uow.merge_records.update(record)
            uow.audit.record(action=CustomerEvents.MERGE_REJECTED, actor_user_id=actor_user_id,
                             customer_id=record.master_customer_id, reason=reason,
                             operation_id=operation_id,
                             after_json=json.dumps({"merge_record_id": record.id}))
            self._emit(uow, CustomerEvents.MERGE_REJECTED, record.master_customer_id,
                      operation_id, actor_user_id, merge_record_id=record.id)
        return CustomerResult.ok("Fusión rechazada", entity_id=record.id,
                                 operation_id=operation_id)
