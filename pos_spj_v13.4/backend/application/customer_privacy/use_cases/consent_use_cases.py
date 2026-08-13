"""CustomerConsent use cases: capture, request, confirm, withdraw, mark
not required.

Reuses ``CustomerAuthorizationPolicy``/``CustomerPermissions`` directly
from ``backend.application.customers`` — the ``CONSENT_*`` codes already
live there (CRM-2), under ``CLIENTES.consentimiento.*``. Each: validates
permission, runs in a CustomerPrivacyUnitOfWork, records audit and
enqueues the canonical event. Idempotent on capture/request
(operation_id).
"""

from __future__ import annotations

import json

from backend.application.customers.authorization import CustomerAuthorizationPolicy
from backend.application.customers.permissions import CustomerPermissions
from backend.application.customer_privacy.result import CustomerPrivacyResult
from backend.domain.customer_privacy.entities.customer_consent import CustomerConsent
from backend.domain.customer_privacy.enums import ConsentChannel, ConsentType
from backend.domain.customer_privacy.events import CustomerPrivacyEvents, build_event_payload
from backend.domain.customer_privacy.exceptions import CustomerPrivacyDomainError
from backend.domain.customers.exceptions import CustomerDomainError
from backend.infrastructure.db.repositories.customer_privacy.unit_of_work import (
    CustomerPrivacyUnitOfWork,
)


class _BaseUseCase:
    def __init__(self, authorization: CustomerAuthorizationPolicy | None = None) -> None:
        self._auth = authorization or CustomerAuthorizationPolicy()

    def _emit(self, uow, event_name: str, customer_id: str, consent_id: str, operation_id: str,
              actor_user_id: str, **extra) -> None:
        payload = build_event_payload(event_name, operation_id=operation_id,
                                      customer_id=customer_id, consent_id=consent_id,
                                      user_id=actor_user_id, **extra)
        uow.outbox.enqueue(payload["event_id"], event_name, json.dumps(payload), operation_id)


class CaptureConsentUseCase(_BaseUseCase):
    def execute(
        self, connection, *, actor_user_id: str, customer_id: str, consent_type: str,
        evidence_reference: str, operation_id: str, channel: str = ConsentChannel.OTHER.value,
        expires_at: str | None = None,
    ) -> CustomerPrivacyResult:
        try:
            self._auth.require(actor_user_id, CustomerPermissions.CONSENT_CAPTURE)
        except CustomerDomainError as exc:
            return CustomerPrivacyResult.fail(str(exc), "PERMISSION_DENIED",
                                              operation_id=operation_id)
        with CustomerPrivacyUnitOfWork(connection) as uow:
            existing = uow.consents.get_by_operation_id(operation_id)
            if existing is not None:
                return CustomerPrivacyResult.ok("Consentimiento ya registrado",
                                                entity_id=existing.id, operation_id=operation_id)
            try:
                consent = CustomerConsent.capture(
                    customer_id, ConsentType(consent_type), channel=ConsentChannel(channel),
                    evidence_reference=evidence_reference, captured_by_user_id=actor_user_id,
                    expires_at=expires_at, operation_id=operation_id)
            except (CustomerPrivacyDomainError, ValueError) as exc:
                return CustomerPrivacyResult.fail(str(exc), "VALIDATION",
                                                  operation_id=operation_id)
            uow.consents.save(consent, operation_id=operation_id)
            uow.audit.record(action=CustomerPrivacyEvents.CONSENT_CAPTURED,
                             actor_user_id=actor_user_id, customer_id=customer_id,
                             consent_id=consent.id, reason=f"tipo: {consent_type}",
                             operation_id=operation_id)
            self._emit(uow, CustomerPrivacyEvents.CONSENT_CAPTURED, customer_id, consent.id,
                      operation_id, actor_user_id, consent_type=consent_type)
        return CustomerPrivacyResult.ok("Consentimiento capturado", entity_id=consent.id,
                                        operation_id=operation_id)


class RequestConsentUseCase(_BaseUseCase):
    def execute(
        self, connection, *, actor_user_id: str, customer_id: str, consent_type: str,
        operation_id: str, channel: str = ConsentChannel.OTHER.value,
    ) -> CustomerPrivacyResult:
        try:
            self._auth.require(actor_user_id, CustomerPermissions.CONSENT_CAPTURE)
        except CustomerDomainError as exc:
            return CustomerPrivacyResult.fail(str(exc), "PERMISSION_DENIED",
                                              operation_id=operation_id)
        with CustomerPrivacyUnitOfWork(connection) as uow:
            existing = uow.consents.get_by_operation_id(operation_id)
            if existing is not None:
                return CustomerPrivacyResult.ok("Consentimiento ya solicitado",
                                                entity_id=existing.id, operation_id=operation_id)
            try:
                consent = CustomerConsent.request(
                    customer_id, ConsentType(consent_type), channel=ConsentChannel(channel),
                    captured_by_user_id=actor_user_id, operation_id=operation_id)
            except (CustomerPrivacyDomainError, ValueError) as exc:
                return CustomerPrivacyResult.fail(str(exc), "VALIDATION",
                                                  operation_id=operation_id)
            uow.consents.save(consent, operation_id=operation_id)
            uow.audit.record(action=CustomerPrivacyEvents.CONSENT_REQUESTED,
                             actor_user_id=actor_user_id, customer_id=customer_id,
                             consent_id=consent.id, operation_id=operation_id)
            self._emit(uow, CustomerPrivacyEvents.CONSENT_REQUESTED, customer_id, consent.id,
                      operation_id, actor_user_id)
        return CustomerPrivacyResult.ok("Consentimiento solicitado", entity_id=consent.id,
                                        operation_id=operation_id)


class ConfirmConsentUseCase(_BaseUseCase):
    def execute(self, connection, *, actor_user_id: str, consent_id: str, evidence_reference: str,
                operation_id: str) -> CustomerPrivacyResult:
        try:
            self._auth.require(actor_user_id, CustomerPermissions.CONSENT_CAPTURE)
        except CustomerDomainError as exc:
            return CustomerPrivacyResult.fail(str(exc), "PERMISSION_DENIED",
                                              operation_id=operation_id)
        with CustomerPrivacyUnitOfWork(connection) as uow:
            consent = uow.consents.get(consent_id)
            if consent is None:
                return CustomerPrivacyResult.fail("El consentimiento no existe", "NOT_FOUND",
                                                  operation_id=operation_id)
            try:
                consent.confirm(evidence_reference=evidence_reference)
            except CustomerPrivacyDomainError as exc:
                return CustomerPrivacyResult.fail(str(exc), "VALIDATION",
                                                  operation_id=operation_id)
            uow.consents.update(consent)
            uow.audit.record(action=CustomerPrivacyEvents.CONSENT_CONFIRMED,
                             actor_user_id=actor_user_id, customer_id=consent.customer_id,
                             consent_id=consent.id, operation_id=operation_id)
            self._emit(uow, CustomerPrivacyEvents.CONSENT_CONFIRMED, consent.customer_id,
                      consent.id, operation_id, actor_user_id)
        return CustomerPrivacyResult.ok("Consentimiento confirmado", entity_id=consent_id,
                                        operation_id=operation_id)


class WithdrawConsentUseCase(_BaseUseCase):
    def execute(self, connection, *, actor_user_id: str, consent_id: str, reason: str,
                operation_id: str) -> CustomerPrivacyResult:
        try:
            self._auth.require(actor_user_id, CustomerPermissions.CONSENT_WITHDRAW)
        except CustomerDomainError as exc:
            return CustomerPrivacyResult.fail(str(exc), "PERMISSION_DENIED",
                                              operation_id=operation_id)
        with CustomerPrivacyUnitOfWork(connection) as uow:
            consent = uow.consents.get(consent_id)
            if consent is None:
                return CustomerPrivacyResult.fail("El consentimiento no existe", "NOT_FOUND",
                                                  operation_id=operation_id)
            try:
                consent.withdraw(reason)
            except CustomerPrivacyDomainError as exc:
                return CustomerPrivacyResult.fail(str(exc), "VALIDATION",
                                                  operation_id=operation_id)
            uow.consents.update(consent)
            uow.audit.record(action=CustomerPrivacyEvents.CONSENT_WITHDRAWN,
                             actor_user_id=actor_user_id, customer_id=consent.customer_id,
                             consent_id=consent.id, reason=reason, operation_id=operation_id)
            self._emit(uow, CustomerPrivacyEvents.CONSENT_WITHDRAWN, consent.customer_id,
                      consent.id, operation_id, actor_user_id)
        return CustomerPrivacyResult.ok("Consentimiento retirado", entity_id=consent_id,
                                        operation_id=operation_id)


class MarkConsentNotRequiredUseCase(_BaseUseCase):
    def execute(
        self, connection, *, actor_user_id: str, customer_id: str, consent_type: str,
        operation_id: str, reason: str = "",
    ) -> CustomerPrivacyResult:
        try:
            self._auth.require(actor_user_id, CustomerPermissions.CONSENT_CAPTURE)
        except CustomerDomainError as exc:
            return CustomerPrivacyResult.fail(str(exc), "PERMISSION_DENIED",
                                              operation_id=operation_id)
        with CustomerPrivacyUnitOfWork(connection) as uow:
            try:
                consent = CustomerConsent.mark_not_required(
                    customer_id, ConsentType(consent_type), reason=reason,
                    captured_by_user_id=actor_user_id, operation_id=operation_id)
            except (CustomerPrivacyDomainError, ValueError) as exc:
                return CustomerPrivacyResult.fail(str(exc), "VALIDATION",
                                                  operation_id=operation_id)
            uow.consents.save(consent, operation_id=operation_id)
            uow.audit.record(action=CustomerPrivacyEvents.CONSENT_MARKED_NOT_REQUIRED,
                             actor_user_id=actor_user_id, customer_id=customer_id,
                             consent_id=consent.id, reason=reason, operation_id=operation_id)
            self._emit(uow, CustomerPrivacyEvents.CONSENT_MARKED_NOT_REQUIRED, customer_id,
                      consent.id, operation_id, actor_user_id)
        return CustomerPrivacyResult.ok("Consentimiento marcado como no requerido",
                                        entity_id=consent.id, operation_id=operation_id)
