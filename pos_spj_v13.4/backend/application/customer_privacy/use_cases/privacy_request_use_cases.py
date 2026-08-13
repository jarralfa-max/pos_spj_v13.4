"""CustomerPrivacyRequest workflow use cases: create, validate, start
processing, complete, reject, cancel.

``ANONYMIZATION``/``CANCELLATION`` requests do NOT complete through
``CompletePrivacyRequestUseCase`` — see
``backend/application/customer_privacy/use_cases/
anonymize_customer_use_case.py`` for their tighter, hot-auth-gated path.
``CompletePrivacyRequestUseCase`` raises rather than silently completing an
anonymization-shaped request, so a caller can't accidentally bypass the
second-approver requirement by calling the generic completion path.
"""

from __future__ import annotations

import json

from backend.application.customers.authorization import CustomerAuthorizationPolicy
from backend.application.customers.permissions import CustomerPermissions
from backend.application.customer_privacy.result import CustomerPrivacyResult
from backend.domain.customer_privacy.entities.customer_privacy_request import (
    CustomerPrivacyRequest,
)
from backend.domain.customer_privacy.enums import PrivacyRequestType
from backend.domain.customer_privacy.events import CustomerPrivacyEvents, build_event_payload
from backend.domain.customer_privacy.exceptions import CustomerPrivacyDomainError
from backend.domain.customers.exceptions import CustomerDomainError
from backend.infrastructure.db.repositories.customer_privacy.unit_of_work import (
    CustomerPrivacyUnitOfWork,
)


class _BaseUseCase:
    def __init__(self, authorization: CustomerAuthorizationPolicy | None = None) -> None:
        self._auth = authorization or CustomerAuthorizationPolicy()

    def _emit(self, uow, event_name: str, customer_id: str, request_id: str, operation_id: str,
              actor_user_id: str, **extra) -> None:
        payload = build_event_payload(event_name, operation_id=operation_id,
                                      customer_id=customer_id, request_id=request_id,
                                      user_id=actor_user_id, **extra)
        uow.outbox.enqueue(payload["event_id"], event_name, json.dumps(payload), operation_id)


class CreatePrivacyRequestUseCase(_BaseUseCase):
    def execute(
        self, connection, *, actor_user_id: str, customer_id: str, request_type: str,
        operation_id: str, description: str = "", related_consent_id: str | None = None,
    ) -> CustomerPrivacyResult:
        try:
            self._auth.require(actor_user_id, CustomerPermissions.PRIVACY_REQUEST_CREATE)
        except CustomerDomainError as exc:
            return CustomerPrivacyResult.fail(str(exc), "PERMISSION_DENIED",
                                              operation_id=operation_id)
        with CustomerPrivacyUnitOfWork(connection) as uow:
            existing = uow.requests.get_by_operation_id(operation_id)
            if existing is not None:
                return CustomerPrivacyResult.ok("Solicitud ya registrada", entity_id=existing.id,
                                                operation_id=operation_id)
            try:
                request = CustomerPrivacyRequest.create(
                    uow.requests.next_code(), customer_id, PrivacyRequestType(request_type),
                    description=description, related_consent_id=related_consent_id,
                    logged_by_user_id=actor_user_id, operation_id=operation_id)
            except (CustomerPrivacyDomainError, ValueError) as exc:
                return CustomerPrivacyResult.fail(str(exc), "VALIDATION",
                                                  operation_id=operation_id)
            uow.requests.save(request, operation_id=operation_id)
            uow.audit.record(action=CustomerPrivacyEvents.PRIVACY_REQUEST_RECEIVED,
                             actor_user_id=actor_user_id, customer_id=customer_id,
                             request_id=request.id, reason=f"tipo: {request_type}",
                             operation_id=operation_id)
            self._emit(uow, CustomerPrivacyEvents.PRIVACY_REQUEST_RECEIVED, customer_id,
                      request.id, operation_id, actor_user_id, request_type=request_type)
        return CustomerPrivacyResult.ok("Solicitud de privacidad registrada",
                                        entity_id=request.id, operation_id=operation_id,
                                        code=str(request.code))


class _TransitionUseCase(_BaseUseCase):
    permission = ""
    event_name = ""

    def _apply(self, request: CustomerPrivacyRequest, *, actor_user_id: str,
               reason: str) -> None:
        raise NotImplementedError

    def execute(self, connection, *, actor_user_id: str, request_id: str, operation_id: str,
                reason: str = "") -> CustomerPrivacyResult:
        try:
            self._auth.require(actor_user_id, self.permission)
        except CustomerDomainError as exc:
            return CustomerPrivacyResult.fail(str(exc), "PERMISSION_DENIED",
                                              operation_id=operation_id)
        with CustomerPrivacyUnitOfWork(connection) as uow:
            request = uow.requests.get(request_id)
            if request is None:
                return CustomerPrivacyResult.fail("La solicitud no existe", "NOT_FOUND",
                                                  operation_id=operation_id)
            try:
                self._apply(request, actor_user_id=actor_user_id, reason=reason)
            except CustomerPrivacyDomainError as exc:
                return CustomerPrivacyResult.fail(str(exc), "VALIDATION",
                                                  operation_id=operation_id)
            uow.requests.update(request)
            uow.audit.record(action=self.event_name, actor_user_id=actor_user_id,
                             customer_id=request.customer_id, request_id=request.id,
                             reason=reason, operation_id=operation_id)
            self._emit(uow, self.event_name, request.customer_id, request.id, operation_id,
                      actor_user_id)
        return CustomerPrivacyResult.ok("Operación registrada", entity_id=request_id,
                                        operation_id=operation_id)


class ValidatePrivacyRequestUseCase(_TransitionUseCase):
    permission = CustomerPermissions.PRIVACY_REQUEST_PROCESS
    event_name = CustomerPrivacyEvents.PRIVACY_REQUEST_VALIDATING

    def _apply(self, request, *, actor_user_id, reason):
        request.validate(actor_user_id)


class StartProcessingPrivacyRequestUseCase(_TransitionUseCase):
    permission = CustomerPermissions.PRIVACY_REQUEST_PROCESS
    event_name = CustomerPrivacyEvents.PRIVACY_REQUEST_IN_PROGRESS

    def _apply(self, request, *, actor_user_id, reason):
        request.start_processing(actor_user_id)


class RejectPrivacyRequestUseCase(_TransitionUseCase):
    permission = CustomerPermissions.PRIVACY_REQUEST_PROCESS
    event_name = CustomerPrivacyEvents.PRIVACY_REQUEST_REJECTED

    def _apply(self, request, *, actor_user_id, reason):
        request.reject(reason)


class CancelPrivacyRequestUseCase(_TransitionUseCase):
    permission = CustomerPermissions.PRIVACY_REQUEST_PROCESS
    event_name = CustomerPrivacyEvents.PRIVACY_REQUEST_CANCELLED

    def _apply(self, request, *, actor_user_id, reason):
        request.cancel(reason)


class CompletePrivacyRequestUseCase(_BaseUseCase):
    """Generic completion for ACCESS/RECTIFICATION/OPPOSITION/EXPORT
    requests, and for CONSENT_WITHDRAWAL (which also withdraws the linked
    consent record in the same transaction). ANONYMIZATION/CANCELLATION
    must go through ``AnonymizeCustomerUseCase`` instead — see this
    module's docstring."""

    def execute(self, connection, *, actor_user_id: str, request_id: str, operation_id: str,
                resolution_notes: str = "") -> CustomerPrivacyResult:
        try:
            self._auth.require(actor_user_id, CustomerPermissions.PRIVACY_REQUEST_PROCESS)
        except CustomerDomainError as exc:
            return CustomerPrivacyResult.fail(str(exc), "PERMISSION_DENIED",
                                              operation_id=operation_id)
        with CustomerPrivacyUnitOfWork(connection) as uow:
            request = uow.requests.get(request_id)
            if request is None:
                return CustomerPrivacyResult.fail("La solicitud no existe", "NOT_FOUND",
                                                  operation_id=operation_id)
            if request.requires_anonymization_workflow():
                return CustomerPrivacyResult.fail(
                    "Las solicitudes de anonimización/cancelación requieren "
                    "AnonymizeCustomerUseCase (segunda autorización)", "VALIDATION",
                    operation_id=operation_id)
            try:
                request.complete(resolution_notes)
                if (request.request_type is PrivacyRequestType.CONSENT_WITHDRAWAL
                        and request.related_consent_id):
                    consent = uow.consents.get(request.related_consent_id)
                    if consent is not None and consent.status.value == "GRANTED":
                        consent.withdraw(f"solicitud de privacidad {request.code}")
                        uow.consents.update(consent)
            except CustomerPrivacyDomainError as exc:
                return CustomerPrivacyResult.fail(str(exc), "VALIDATION",
                                                  operation_id=operation_id)
            uow.requests.update(request)
            uow.audit.record(action=CustomerPrivacyEvents.PRIVACY_REQUEST_COMPLETED,
                             actor_user_id=actor_user_id, customer_id=request.customer_id,
                             request_id=request.id, operation_id=operation_id)
            self._emit(uow, CustomerPrivacyEvents.PRIVACY_REQUEST_COMPLETED,
                      request.customer_id, request.id, operation_id, actor_user_id)
        return CustomerPrivacyResult.ok("Solicitud completada", entity_id=request_id,
                                        operation_id=operation_id)
