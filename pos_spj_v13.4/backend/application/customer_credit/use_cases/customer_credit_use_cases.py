"""CustomerCreditProfile workflow use cases: request, review, approve,
reject, update limit (+ extraordinary override), suspend, block, reopen,
close (§37-40's named workflow, plus ``ReopenCustomerCreditUseCase`` —
implied by the pre-existing ``CREDIT_REOPEN`` permission even though not
literally named in §37-40's use-case list, same "don't leave a permission
orphaned" call already made for CRM-6's ``TASKS_RESCHEDULE``/
``REMINDERS_CREATE`` and CRM-7's ``SLA_MANAGE``/``SLA_OVERRIDE``).

Reuses ``CustomerAuthorizationPolicy``/``CustomerPermissions`` directly
from ``backend.application.customers`` — the ``CREDIT_*`` permission codes
already live there (CRM-2), under the ``CLIENTES.credito.*`` namespace, not
``CRM.*`` (credit is a facet of the customer record, not the commercial-
relationship module) — same cross-package reuse discipline CRM-7 already
established for Service Cases against the ``crm`` stack.

Each: validates permission, runs in a CustomerCreditUnitOfWork, records
audit and enqueues the canonical event to the outbox. Idempotent on request
(operation_id).
"""

from __future__ import annotations

import json

from backend.application.customers.authorization import CustomerAuthorizationPolicy
from backend.application.customers.permissions import CustomerPermissions
from backend.application.customer_credit.result import CustomerCreditResult
from backend.domain.customer_credit.entities.customer_credit_profile import CustomerCreditProfile
from backend.domain.customer_credit.enums import CreditRiskLevel
from backend.domain.customer_credit.events import CustomerCreditEvents, build_event_payload
from backend.domain.customer_credit.exceptions import CustomerCreditDomainError
from backend.domain.customers.exceptions import CustomerDomainError
from backend.domain.customers.policies.segregation_of_duties_policy import (
    CustomerSegregationOfDutiesPolicy,
)
from backend.infrastructure.db.repositories.customer_credit.unit_of_work import (
    CustomerCreditUnitOfWork,
)


class _BaseUseCase:
    def __init__(self, authorization: CustomerAuthorizationPolicy | None = None) -> None:
        self._auth = authorization or CustomerAuthorizationPolicy()

    def _emit(self, uow, event_name: str, customer_id: str, profile_id: str, operation_id: str,
              actor_user_id: str, **extra) -> None:
        payload = build_event_payload(event_name, operation_id=operation_id,
                                      customer_id=customer_id, profile_id=profile_id,
                                      user_id=actor_user_id, **extra)
        uow.outbox.enqueue(payload["event_id"], event_name, json.dumps(payload), operation_id)


class RequestCustomerCreditUseCase(_BaseUseCase):
    def execute(
        self, connection, *, actor_user_id: str, customer_id: str, operation_id: str,
        requested_limit="0", payment_terms_days: int = 0,
    ) -> CustomerCreditResult:
        try:
            self._auth.require(actor_user_id, CustomerPermissions.CREDIT_REQUEST)
        except CustomerDomainError as exc:
            return CustomerCreditResult.fail(str(exc), "PERMISSION_DENIED",
                                             operation_id=operation_id)
        with CustomerCreditUnitOfWork(connection) as uow:
            existing = uow.profiles.get_by_operation_id(operation_id)
            if existing is not None:
                return CustomerCreditResult.ok("Solicitud ya registrada", entity_id=existing.id,
                                               operation_id=operation_id)
            if uow.profiles.get_by_customer_id(customer_id) is not None:
                return CustomerCreditResult.fail(
                    "El cliente ya tiene un perfil de crédito", "VALIDATION",
                    operation_id=operation_id)
            try:
                profile = CustomerCreditProfile.request(
                    customer_id, actor_user_id, requested_limit=requested_limit,
                    payment_terms_days=payment_terms_days, operation_id=operation_id)
            except (CustomerCreditDomainError, ValueError) as exc:
                return CustomerCreditResult.fail(str(exc), "VALIDATION",
                                                 operation_id=operation_id)
            uow.profiles.save(profile, operation_id=operation_id)
            uow.audit.record(action=CustomerCreditEvents.CREDIT_REQUESTED,
                             actor_user_id=actor_user_id, customer_id=customer_id,
                             profile_id=profile.id, reason="solicitud",
                             operation_id=operation_id)
            self._emit(uow, CustomerCreditEvents.CREDIT_REQUESTED, customer_id, profile.id,
                      operation_id, actor_user_id)
        return CustomerCreditResult.ok("Solicitud de crédito registrada", entity_id=profile.id,
                                       operation_id=operation_id)


class _TransitionUseCase(_BaseUseCase):
    permission = ""
    event_name = ""

    def _apply(self, profile: CustomerCreditProfile, *, actor_user_id: str,
               reason: str) -> None:
        raise NotImplementedError

    def execute(self, connection, *, actor_user_id: str, customer_id: str, operation_id: str,
                reason: str = "") -> CustomerCreditResult:
        try:
            self._auth.require(actor_user_id, self.permission)
        except CustomerDomainError as exc:
            return CustomerCreditResult.fail(str(exc), "PERMISSION_DENIED",
                                             operation_id=operation_id)
        with CustomerCreditUnitOfWork(connection) as uow:
            profile = uow.profiles.get_by_customer_id(customer_id)
            if profile is None:
                return CustomerCreditResult.fail(
                    "El cliente no tiene un perfil de crédito", "NOT_FOUND",
                    operation_id=operation_id)
            try:
                self._apply(profile, actor_user_id=actor_user_id, reason=reason)
            except CustomerCreditDomainError as exc:
                return CustomerCreditResult.fail(str(exc), "VALIDATION",
                                                 operation_id=operation_id)
            uow.profiles.update(profile)
            uow.audit.record(action=self.event_name, actor_user_id=actor_user_id,
                             customer_id=customer_id, profile_id=profile.id, reason=reason,
                             operation_id=operation_id)
            self._emit(uow, self.event_name, customer_id, profile.id, operation_id,
                      actor_user_id)
        return CustomerCreditResult.ok("Operación registrada", entity_id=profile.id,
                                       operation_id=operation_id)


class ReviewCustomerCreditUseCase(_TransitionUseCase):
    permission = CustomerPermissions.CREDIT_REVIEW
    event_name = CustomerCreditEvents.CREDIT_REVIEWED

    def __init__(self, authorization=None, *, risk_level: CreditRiskLevel | None = None) -> None:
        super().__init__(authorization)
        self._risk_level = risk_level

    def execute(self, connection, *, actor_user_id, customer_id, operation_id,
                risk_level: str | None = None, reason: str = "") -> CustomerCreditResult:
        self._risk_level = CreditRiskLevel(risk_level) if risk_level else None
        return super().execute(connection, actor_user_id=actor_user_id, customer_id=customer_id,
                               operation_id=operation_id, reason=reason)

    def _apply(self, profile, *, actor_user_id, reason):
        profile.review(risk_level=self._risk_level)


class RejectCustomerCreditUseCase(_TransitionUseCase):
    permission = CustomerPermissions.CREDIT_REJECT
    event_name = CustomerCreditEvents.CREDIT_REJECTED

    def _apply(self, profile, *, actor_user_id, reason):
        profile.reject(reason)


class SuspendCustomerCreditUseCase(_TransitionUseCase):
    permission = CustomerPermissions.CREDIT_SUSPEND
    event_name = CustomerCreditEvents.CREDIT_SUSPENDED

    def _apply(self, profile, *, actor_user_id, reason):
        profile.suspend(reason)


class BlockCustomerCreditUseCase(_TransitionUseCase):
    permission = CustomerPermissions.CREDIT_BLOCK
    event_name = CustomerCreditEvents.CREDIT_BLOCKED

    def _apply(self, profile, *, actor_user_id, reason):
        profile.block(reason)


class ReopenCustomerCreditUseCase(_TransitionUseCase):
    permission = CustomerPermissions.CREDIT_REOPEN
    event_name = CustomerCreditEvents.CREDIT_REOPENED

    def _apply(self, profile, *, actor_user_id, reason):
        profile.reopen(reason)


class CloseCustomerCreditUseCase(_TransitionUseCase):
    permission = CustomerPermissions.CREDIT_CLOSE
    event_name = CustomerCreditEvents.CREDIT_CLOSED

    def _apply(self, profile, *, actor_user_id, reason):
        profile.close(reason)


class ApproveCustomerCreditUseCase(_BaseUseCase):
    """§73: "Quien solicita crédito no aprueba su propia solicitud" —
    enforced via CRM-2's ``CustomerSegregationOfDutiesPolicy.
    enforce_credit_requester_not_self_approving``, built for exactly this
    use case and unconsumed until now."""

    def __init__(self, authorization: CustomerAuthorizationPolicy | None = None) -> None:
        super().__init__(authorization)
        self._sod = CustomerSegregationOfDutiesPolicy()

    def execute(
        self, connection, *, actor_user_id: str, customer_id: str, operation_id: str,
        credit_limit=None, payment_terms_days: int | None = None, risk_level: str | None = None,
    ) -> CustomerCreditResult:
        try:
            self._auth.require(actor_user_id, CustomerPermissions.CREDIT_APPROVE)
        except CustomerDomainError as exc:
            return CustomerCreditResult.fail(str(exc), "PERMISSION_DENIED",
                                             operation_id=operation_id)
        with CustomerCreditUnitOfWork(connection) as uow:
            profile = uow.profiles.get_by_customer_id(customer_id)
            if profile is None:
                return CustomerCreditResult.fail(
                    "El cliente no tiene un perfil de crédito", "NOT_FOUND",
                    operation_id=operation_id)
            try:
                self._sod.enforce_credit_requester_not_self_approving(
                    profile.requested_by_user_id, actor_user_id)
                profile.approve(
                    actor_user_id, credit_limit=credit_limit,
                    payment_terms_days=payment_terms_days,
                    risk_level=CreditRiskLevel(risk_level) if risk_level else None)
            except CustomerCreditDomainError as exc:
                return CustomerCreditResult.fail(str(exc), "VALIDATION",
                                                 operation_id=operation_id)
            except CustomerDomainError as exc:
                return CustomerCreditResult.fail(str(exc), "SEGREGATION_OF_DUTIES",
                                                 operation_id=operation_id)
            uow.profiles.update(profile)
            uow.audit.record(action=CustomerCreditEvents.CREDIT_APPROVED,
                             actor_user_id=actor_user_id, customer_id=customer_id,
                             profile_id=profile.id, authorized_by_user_id=actor_user_id,
                             after_json=json.dumps({"credit_limit": str(profile.credit_limit)}),
                             reason="aprobación", operation_id=operation_id)
            self._emit(uow, CustomerCreditEvents.CREDIT_APPROVED, customer_id, profile.id,
                      operation_id, actor_user_id, credit_limit=str(profile.credit_limit))
        return CustomerCreditResult.ok("Crédito aprobado", entity_id=profile.id,
                                       operation_id=operation_id,
                                       credit_limit=str(profile.credit_limit))


class UpdateCustomerCreditLimitUseCase(_BaseUseCase):
    """§74 hot authorization: an "extraordinary" limit increase
    (``override=True``) requires a second, distinct authorizer — built on
    CRM-2's ``CustomerAuthorizationPolicy.authorize_exception()`` and
    ``CustomerAuthorizationGrant`` (unconsumed since CRM-2). A routine
    change (``override=False``) only needs ``CREDIT_LIMIT_EDIT`` from the
    single acting user."""

    def execute(
        self, connection, *, actor_user_id: str, customer_id: str, new_limit, operation_id: str,
        override: bool = False, requested_by_user_id: str | None = None, reason: str = "",
    ) -> CustomerCreditResult:
        if override:
            try:
                grant = self._auth.authorize_exception(
                    authorizer_user_id=actor_user_id,
                    requested_by=requested_by_user_id or actor_user_id,
                    permission_code=CustomerPermissions.CREDIT_LIMIT_OVERRIDE,
                    operation_id=operation_id, reason=reason, credit_amount=new_limit)
            except CustomerDomainError as exc:
                return CustomerCreditResult.fail(str(exc), "PERMISSION_DENIED",
                                                 operation_id=operation_id)
        else:
            try:
                self._auth.require(actor_user_id, CustomerPermissions.CREDIT_LIMIT_EDIT)
            except CustomerDomainError as exc:
                return CustomerCreditResult.fail(str(exc), "PERMISSION_DENIED",
                                                 operation_id=operation_id)
            grant = None
        with CustomerCreditUnitOfWork(connection) as uow:
            profile = uow.profiles.get_by_customer_id(customer_id)
            if profile is None:
                return CustomerCreditResult.fail(
                    "El cliente no tiene un perfil de crédito", "NOT_FOUND",
                    operation_id=operation_id)
            try:
                profile.update_limit(new_limit, authorized_by_user_id=actor_user_id)
            except CustomerCreditDomainError as exc:
                return CustomerCreditResult.fail(str(exc), "VALIDATION",
                                                 operation_id=operation_id)
            uow.profiles.update(profile)
            event_name = (CustomerCreditEvents.CREDIT_LIMIT_OVERRIDDEN if override
                          else CustomerCreditEvents.CREDIT_LIMIT_UPDATED)
            after = {"new_limit": str(profile.credit_limit)}
            if grant is not None:
                after.update({"requested_by": grant.requested_by, "authorized_by": grant.authorized_by})
            uow.audit.record(action=event_name, actor_user_id=actor_user_id,
                             customer_id=customer_id, profile_id=profile.id,
                             authorized_by_user_id=(grant.authorized_by if grant else actor_user_id),
                             after_json=json.dumps(after), reason=reason,
                             operation_id=operation_id)
            self._emit(uow, event_name, customer_id, profile.id, operation_id, actor_user_id,
                      new_limit=str(profile.credit_limit))
        return CustomerCreditResult.ok("Límite de crédito actualizado", entity_id=profile.id,
                                       operation_id=operation_id,
                                       credit_limit=str(profile.credit_limit))
