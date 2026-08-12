"""CustomerServiceCase use cases: create, update, assign/reassign, start,
wait-for-customer/wait-internal, resume, record first response, resolve,
close, cancel, reopen.

Reuses ``CRMAuthorizationPolicy``/``CRMPermissions`` directly from
``backend.application.crm`` — CRM-2 built one authorization stack for the
whole Leads/Opportunities/Activities/Cases family and ``CASES_*``/``SLA_*``
permissions already live there; duplicating a parallel
``CustomerServiceAuthorizationPolicy`` would just be the same concept under
a different name (see backend/domain/customer_service/exceptions.py's
docstring).

Each: validates permission, runs in a CustomerServiceUnitOfWork, records
audit and enqueues the canonical event to the outbox. Idempotent on create
(operation_id). Mirrors
backend/application/crm/use_cases/opportunity_use_cases.py.
"""

from __future__ import annotations

import json

from backend.application.crm.authorization import CRMAuthorizationPolicy
from backend.application.crm.permissions import CRMPermissions
from backend.application.customer_service.result import CustomerServiceResult
from backend.domain.customer_service.entities.customer_service_case import CustomerServiceCase
from backend.domain.customer_service.entities.service_case_resolution import (
    ServiceCaseResolution,
)
from backend.domain.customer_service.entities.sla_instance import SLAInstance
from backend.domain.customer_service.enums import (
    ServiceCaseChannel,
    ServiceCasePriority,
    ServiceCaseType,
)
from backend.domain.customer_service.events import CustomerServiceEvents, build_event_payload
from backend.domain.customer_service.exceptions import CustomerServiceDomainError
from backend.domain.customer_service.policies.service_level_policy_resolver import (
    ServiceLevelPolicyResolver,
)
from backend.domain.crm.exceptions import CRMDomainError
from backend.infrastructure.db.repositories.customer_service.unit_of_work import (
    CustomerServiceUnitOfWork,
)


class _BaseUseCase:
    def __init__(self, authorization: CRMAuthorizationPolicy | None = None) -> None:
        self._auth = authorization or CRMAuthorizationPolicy()

    def _emit(self, uow, event_name: str, case_id: str, operation_id: str,
              actor_user_id: str, **extra) -> None:
        payload = build_event_payload(event_name, operation_id=operation_id, case_id=case_id,
                                      user_id=actor_user_id, **extra)
        uow.outbox.enqueue(payload["event_id"], event_name, json.dumps(payload), operation_id)


class CreateServiceCaseUseCase(_BaseUseCase):
    def __init__(self, authorization: CRMAuthorizationPolicy | None = None) -> None:
        super().__init__(authorization)
        self._resolver = ServiceLevelPolicyResolver()

    def execute(
        self, connection, *, actor_user_id: str, customer_id: str, case_type: str, subject: str,
        operation_id: str, priority: str = ServiceCasePriority.NORMAL.value,
        category_id: str | None = None, description: str = "",
        channel: str = ServiceCaseChannel.OTHER.value, origin_branch_id: str | None = None,
        territory_id: str | None = None, is_sensitive: bool = False,
    ) -> CustomerServiceResult:
        try:
            self._auth.require(actor_user_id, CRMPermissions.CASES_CREATE)
        except CRMDomainError as exc:
            return CustomerServiceResult.fail(str(exc), "PERMISSION_DENIED",
                                              operation_id=operation_id)
        with CustomerServiceUnitOfWork(connection) as uow:
            existing = uow.cases.get_by_operation_id(operation_id)
            if existing is not None:
                return CustomerServiceResult.ok("Caso ya registrado", entity_id=existing.id,
                                                operation_id=operation_id)
            try:
                case_type_enum = ServiceCaseType(case_type)
                priority_enum = ServiceCasePriority(priority)
                channel_enum = ServiceCaseChannel(channel)
                case = CustomerServiceCase.create(
                    uow.cases.next_code(), customer_id, case_type_enum, subject,
                    priority=priority_enum, category_id=category_id, description=description,
                    channel=channel_enum, origin_branch_id=origin_branch_id,
                    territory_id=territory_id, is_sensitive=is_sensitive,
                    created_by_user_id=actor_user_id, operation_id=operation_id)
            except (CustomerServiceDomainError, ValueError) as exc:
                return CustomerServiceResult.fail(str(exc), "VALIDATION",
                                                  operation_id=operation_id)
            uow.cases.save(case, operation_id=operation_id)

            policy = self._resolver.resolve(
                uow.policies.list_active(), case_type=case_type_enum, priority=priority_enum,
                origin_branch_id=origin_branch_id, channel=channel_enum)
            if policy is not None:
                sla = SLAInstance.create(
                    case.id, policy.id, policy.first_response_minutes,
                    policy.resolution_minutes, at_risk_threshold_pct=policy.at_risk_threshold_pct,
                    reference_time=case.created_at)
                uow.sla_instances.save(sla)

            uow.audit.record(action=CustomerServiceEvents.CASE_CREATED,
                             actor_user_id=actor_user_id, case_id=case.id,
                             after_json=json.dumps({"subject": subject, "customer_id": customer_id}),
                             reason="alta", operation_id=operation_id)
            self._emit(uow, CustomerServiceEvents.CASE_CREATED, case.id, operation_id,
                      actor_user_id)
        return CustomerServiceResult.ok("Caso creado", entity_id=case.id,
                                        operation_id=operation_id, code=str(case.code))


class UpdateServiceCaseUseCase(_BaseUseCase):
    def execute(
        self, connection, *, actor_user_id: str, case_id: str, operation_id: str,
        subject: str | None = None, description: str | None = None, priority: str | None = None,
        category_id: str | None = None,
    ) -> CustomerServiceResult:
        try:
            self._auth.require(actor_user_id, CRMPermissions.CASES_EDIT)
        except CRMDomainError as exc:
            return CustomerServiceResult.fail(str(exc), "PERMISSION_DENIED",
                                              operation_id=operation_id)
        with CustomerServiceUnitOfWork(connection) as uow:
            case = uow.cases.get(case_id)
            if case is None:
                return CustomerServiceResult.fail("El caso no existe", "NOT_FOUND",
                                                  operation_id=operation_id)
            if subject is not None:
                if not subject.strip():
                    return CustomerServiceResult.fail("subject no puede quedar vacío",
                                                      "VALIDATION", operation_id=operation_id)
                case.subject = subject.strip()
            if description is not None:
                case.description = description
            if priority is not None:
                try:
                    case.priority = ServiceCasePriority(priority)
                except ValueError as exc:
                    return CustomerServiceResult.fail(str(exc), "VALIDATION",
                                                      operation_id=operation_id)
            if category_id is not None:
                case.category_id = category_id
            case.record_edit()
            uow.cases.update(case)
            uow.audit.record(action=CustomerServiceEvents.CASE_UPDATED,
                             actor_user_id=actor_user_id, case_id=case.id, reason="edición",
                             operation_id=operation_id)
            self._emit(uow, CustomerServiceEvents.CASE_UPDATED, case.id, operation_id,
                      actor_user_id)
        return CustomerServiceResult.ok("Caso actualizado", entity_id=case_id,
                                        operation_id=operation_id)


class AssignServiceCaseUseCase(_BaseUseCase):
    """Requires CASES_ASSIGN for the first assignment (no prior owner) and
    CASES_REASSIGN when handing an already-owned case to someone else —
    same pattern as AssignOpportunityUseCase (CRM-5)/AssignCRMTaskUseCase
    (CRM-6)."""

    def execute(self, connection, *, actor_user_id: str, case_id: str, assignee_user_id: str,
                operation_id: str) -> CustomerServiceResult:
        with CustomerServiceUnitOfWork(connection) as uow:
            case = uow.cases.get(case_id)
            if case is None:
                return CustomerServiceResult.fail("El caso no existe", "NOT_FOUND",
                                                  operation_id=operation_id)
            permission = (CRMPermissions.CASES_REASSIGN if case.assigned_user_id
                          else CRMPermissions.CASES_ASSIGN)
            try:
                self._auth.require(actor_user_id, permission)
            except CRMDomainError as exc:
                return CustomerServiceResult.fail(str(exc), "PERMISSION_DENIED",
                                                  operation_id=operation_id)
            try:
                case.assign_owner(assignee_user_id)
            except CustomerServiceDomainError as exc:
                return CustomerServiceResult.fail(str(exc), "VALIDATION",
                                                  operation_id=operation_id)
            uow.cases.update(case)
            uow.audit.record(action=CustomerServiceEvents.CASE_ASSIGNED,
                             actor_user_id=actor_user_id, case_id=case.id,
                             operation_id=operation_id)
            self._emit(uow, CustomerServiceEvents.CASE_ASSIGNED, case.id, operation_id,
                      actor_user_id, assignee_user_id=assignee_user_id)
        return CustomerServiceResult.ok("Caso asignado", entity_id=case_id,
                                        operation_id=operation_id)


class _TransitionUseCase(_BaseUseCase):
    permission = ""
    event_name = ""

    def _apply(self, uow, case: CustomerServiceCase, *, actor_user_id: str,
               reason: str) -> None:
        raise NotImplementedError

    def execute(self, connection, *, actor_user_id: str, case_id: str, operation_id: str,
                reason: str = "") -> CustomerServiceResult:
        try:
            self._auth.require(actor_user_id, self.permission)
        except CRMDomainError as exc:
            return CustomerServiceResult.fail(str(exc), "PERMISSION_DENIED",
                                              operation_id=operation_id)
        with CustomerServiceUnitOfWork(connection) as uow:
            case = uow.cases.get(case_id)
            if case is None:
                return CustomerServiceResult.fail("El caso no existe", "NOT_FOUND",
                                                  operation_id=operation_id)
            try:
                self._apply(uow, case, actor_user_id=actor_user_id, reason=reason)
            except CustomerServiceDomainError as exc:
                return CustomerServiceResult.fail(str(exc), "VALIDATION",
                                                  operation_id=operation_id)
            uow.cases.update(case)
            uow.audit.record(action=self.event_name, actor_user_id=actor_user_id,
                             case_id=case.id, reason=reason, operation_id=operation_id)
            self._emit(uow, self.event_name, case.id, operation_id, actor_user_id)
        return CustomerServiceResult.ok("Operación registrada", entity_id=case_id,
                                        operation_id=operation_id)


class StartServiceCaseProgressUseCase(_TransitionUseCase):
    permission = CRMPermissions.CASES_EDIT
    event_name = CustomerServiceEvents.CASE_STARTED

    def _apply(self, uow, case, *, actor_user_id, reason):
        case.start_progress()


class WaitForCustomerUseCase(_TransitionUseCase):
    permission = CRMPermissions.CASES_EDIT
    event_name = CustomerServiceEvents.CASE_WAITING_CUSTOMER

    def _apply(self, uow, case, *, actor_user_id, reason):
        case.wait_for_customer()
        sla = uow.sla_instances.get_for_case(case.id)
        if sla is not None:
            sla.pause()
            uow.sla_instances.update(sla)


class WaitInternalUseCase(_TransitionUseCase):
    permission = CRMPermissions.CASES_EDIT
    event_name = CustomerServiceEvents.CASE_WAITING_INTERNAL

    def _apply(self, uow, case, *, actor_user_id, reason):
        case.wait_internal()


class ResumeServiceCaseUseCase(_TransitionUseCase):
    permission = CRMPermissions.CASES_EDIT
    event_name = CustomerServiceEvents.CASE_RESUMED

    def _apply(self, uow, case, *, actor_user_id, reason):
        case.resume()
        sla = uow.sla_instances.get_for_case(case.id)
        if sla is not None:
            sla.resume()
            uow.sla_instances.update(sla)


class CancelServiceCaseUseCase(_TransitionUseCase):
    permission = CRMPermissions.CASES_EDIT
    event_name = CustomerServiceEvents.CASE_CANCELLED

    def _apply(self, uow, case, *, actor_user_id, reason):
        case.cancel(reason)


class CloseServiceCaseUseCase(_TransitionUseCase):
    permission = CRMPermissions.CASES_CLOSE
    event_name = CustomerServiceEvents.CASE_CLOSED

    def _apply(self, uow, case, *, actor_user_id, reason):
        case.close()


class ReopenServiceCaseUseCase(_TransitionUseCase):
    permission = CRMPermissions.CASES_REOPEN
    event_name = CustomerServiceEvents.CASE_REOPENED

    def _apply(self, uow, case, *, actor_user_id, reason):
        case.reopen(reason)


class RecordFirstResponseUseCase(_BaseUseCase):
    def execute(self, connection, *, actor_user_id: str, case_id: str,
                operation_id: str) -> CustomerServiceResult:
        try:
            self._auth.require(actor_user_id, CRMPermissions.CASES_EDIT)
        except CRMDomainError as exc:
            return CustomerServiceResult.fail(str(exc), "PERMISSION_DENIED",
                                              operation_id=operation_id)
        with CustomerServiceUnitOfWork(connection) as uow:
            case = uow.cases.get(case_id)
            if case is None:
                return CustomerServiceResult.fail("El caso no existe", "NOT_FOUND",
                                                  operation_id=operation_id)
            sla = uow.sla_instances.get_for_case(case_id)
            if sla is None:
                return CustomerServiceResult.fail(
                    "El caso no tiene una SLA asociada", "NOT_FOUND", operation_id=operation_id)
            try:
                sla.record_first_response()
            except CustomerServiceDomainError as exc:
                return CustomerServiceResult.fail(str(exc), "VALIDATION",
                                                  operation_id=operation_id)
            uow.sla_instances.update(sla)
            uow.audit.record(action=CustomerServiceEvents.SLA_FIRST_RESPONSE_RECORDED,
                             actor_user_id=actor_user_id, case_id=case_id,
                             operation_id=operation_id)
            self._emit(uow, CustomerServiceEvents.SLA_FIRST_RESPONSE_RECORDED, case_id,
                      operation_id, actor_user_id)
        return CustomerServiceResult.ok("Primera respuesta registrada", entity_id=case_id,
                                        operation_id=operation_id)


class ResolveServiceCaseUseCase(_BaseUseCase):
    def execute(
        self, connection, *, actor_user_id: str, case_id: str, resolution_summary: str,
        operation_id: str, root_cause: str = "", customer_satisfied: bool | None = None,
    ) -> CustomerServiceResult:
        try:
            self._auth.require(actor_user_id, CRMPermissions.CASES_RESOLVE)
        except CRMDomainError as exc:
            return CustomerServiceResult.fail(str(exc), "PERMISSION_DENIED",
                                              operation_id=operation_id)
        with CustomerServiceUnitOfWork(connection) as uow:
            case = uow.cases.get(case_id)
            if case is None:
                return CustomerServiceResult.fail("El caso no existe", "NOT_FOUND",
                                                  operation_id=operation_id)
            try:
                resolution = ServiceCaseResolution.create(
                    case.id, resolution_summary, actor_user_id, root_cause=root_cause,
                    customer_satisfied=customer_satisfied)
                case.resolve()
            except CustomerServiceDomainError as exc:
                return CustomerServiceResult.fail(str(exc), "VALIDATION",
                                                  operation_id=operation_id)
            uow.cases.update(case)
            uow.resolutions.save(resolution)
            sla = uow.sla_instances.get_for_case(case_id)
            if sla is not None:
                try:
                    sla.record_resolution(at=case.resolved_at)
                except CustomerServiceDomainError:
                    pass
                uow.sla_instances.update(sla)
            uow.audit.record(action=CustomerServiceEvents.CASE_RESOLVED,
                             actor_user_id=actor_user_id, case_id=case.id,
                             reason="resolución", operation_id=operation_id)
            self._emit(uow, CustomerServiceEvents.CASE_RESOLVED, case.id, operation_id,
                      actor_user_id, resolution_id=resolution.id)
        return CustomerServiceResult.ok("Caso resuelto", entity_id=case_id,
                                        operation_id=operation_id, resolution_id=resolution.id)
