"""Customer data-quality issue use cases: scan, acknowledge, correct,
dismiss (§46).

RunCustomerDataQualityScanUseCase evaluates CustomerDataQualityService
against one customer (or every active customer when none is given) and
persists a new OPEN issue per violated rule — idempotent per (customer,
rule): if an OPEN/ACKNOWLEDGED issue for that exact rule already exists, it
is left alone rather than duplicated. Gated by DATA_QUALITY_VIEW, same
"viewing implies refreshing what you view" reasoning as
DetectDuplicateCandidatesUseCase.
"""

from __future__ import annotations

import json

from backend.application.customers.authorization import CustomerAuthorizationPolicy
from backend.application.customers.permissions import CustomerPermissions
from backend.application.customers.result import CustomerResult
from backend.application.customers.services.customer_data_quality_service import (
    CustomerDataQualityService,
)
from backend.domain.customers.entities.customer_data_quality_issue import (
    CustomerDataQualityIssue,
)
from backend.domain.customers.events import CustomerEvents, build_event_payload
from backend.domain.customers.exceptions import CustomerDomainError
from backend.infrastructure.db.repositories.customers.unit_of_work import CustomerUnitOfWork


class _BaseUseCase:
    def __init__(self, authorization: CustomerAuthorizationPolicy | None = None) -> None:
        self._auth = authorization or CustomerAuthorizationPolicy()

    def _emit(self, uow, event_name: str, customer_id: str, operation_id: str,
              actor_user_id: str, **extra) -> None:
        payload = build_event_payload(event_name, operation_id=operation_id,
                                      customer_id=customer_id, user_id=actor_user_id, **extra)
        uow.outbox.enqueue(payload["event_id"], event_name, json.dumps(payload), operation_id)


class RunCustomerDataQualityScanUseCase(_BaseUseCase):
    def __init__(self, authorization: CustomerAuthorizationPolicy | None = None) -> None:
        super().__init__(authorization)
        self._service = CustomerDataQualityService()

    def execute(self, connection, *, actor_user_id: str, operation_id: str,
                customer_id: str | None = None) -> CustomerResult:
        try:
            self._auth.require(actor_user_id, CustomerPermissions.DATA_QUALITY_VIEW)
        except CustomerDomainError as exc:
            return CustomerResult.fail(str(exc), "PERMISSION_DENIED", operation_id=operation_id)
        with CustomerUnitOfWork(connection) as uow:
            if customer_id:
                customer = uow.customers.get(customer_id)
                if customer is None:
                    return CustomerResult.fail("El cliente no existe", "NOT_FOUND",
                                               operation_id=operation_id)
                customers = [customer]
            else:
                customers = uow.customers.list_active(limit=10_000)

            detected_ids: list[str] = []
            for customer in customers:
                tax_profile = uow.tax_profiles.get_for_customer(customer.id)
                contacts = uow.contacts.list_for_customer(customer.id)
                primary = next((c for c in contacts if c.is_primary), None) or (
                    contacts[0] if contacts else None)
                has_address = bool(uow.addresses.list_for_customer(customer.id))
                violations = self._service.evaluate(
                    display_name=customer.display_name,
                    phone_e164=primary.phone_e164 if primary else None,
                    email=primary.email if primary else None,
                    tax_identifier=tax_profile.tax_identifier if tax_profile else None,
                    has_address=has_address)
                for rule_code, description in violations:
                    if uow.data_quality_issues.get_open(customer.id, rule_code.value) is not None:
                        continue
                    pair_operation_id = f"{operation_id}:{customer.id}:{rule_code.value}"
                    issue = CustomerDataQualityIssue.detect(
                        customer.id, rule_code, description, operation_id=pair_operation_id)
                    uow.data_quality_issues.save(issue)
                    uow.audit.record(
                        action=CustomerEvents.DATA_QUALITY_ISSUE_DETECTED,
                        actor_user_id=actor_user_id, customer_id=customer.id,
                        reason=description, operation_id=pair_operation_id,
                        after_json=json.dumps({"issue_id": issue.id,
                                               "rule_code": rule_code.value}))
                    self._emit(uow, CustomerEvents.DATA_QUALITY_ISSUE_DETECTED, customer.id,
                              pair_operation_id, actor_user_id, issue_id=issue.id,
                              rule_code=rule_code.value)
                    detected_ids.append(issue.id)
        return CustomerResult.ok(
            f"{len(detected_ids)} problema(s) de calidad detectado(s)",
            operation_id=operation_id, issue_ids=detected_ids)


class AcknowledgeDataQualityIssueUseCase(_BaseUseCase):
    def execute(self, connection, *, actor_user_id: str, issue_id: str,
                operation_id: str) -> CustomerResult:
        try:
            self._auth.require(actor_user_id, CustomerPermissions.DATA_QUALITY_RESOLVE)
        except CustomerDomainError as exc:
            return CustomerResult.fail(str(exc), "PERMISSION_DENIED", operation_id=operation_id)
        with CustomerUnitOfWork(connection) as uow:
            issue = uow.data_quality_issues.get(issue_id)
            if issue is None:
                return CustomerResult.fail("El problema de calidad no existe", "NOT_FOUND",
                                           operation_id=operation_id)
            try:
                issue.acknowledge(actor_user_id)
            except CustomerDomainError as exc:
                return CustomerResult.fail(str(exc), "VALIDATION", operation_id=operation_id)
            uow.data_quality_issues.update(issue)
            uow.audit.record(action=CustomerEvents.DATA_QUALITY_ISSUE_ACKNOWLEDGED,
                             actor_user_id=actor_user_id, customer_id=issue.customer_id,
                             operation_id=operation_id,
                             after_json=json.dumps({"issue_id": issue.id}))
            self._emit(uow, CustomerEvents.DATA_QUALITY_ISSUE_ACKNOWLEDGED, issue.customer_id,
                      operation_id, actor_user_id, issue_id=issue.id)
        return CustomerResult.ok("Problema reconocido", entity_id=issue.id,
                                 operation_id=operation_id)


class CorrectDataQualityIssueUseCase(_BaseUseCase):
    def execute(self, connection, *, actor_user_id: str, issue_id: str,
                operation_id: str) -> CustomerResult:
        try:
            self._auth.require(actor_user_id, CustomerPermissions.DATA_QUALITY_RESOLVE)
        except CustomerDomainError as exc:
            return CustomerResult.fail(str(exc), "PERMISSION_DENIED", operation_id=operation_id)
        with CustomerUnitOfWork(connection) as uow:
            issue = uow.data_quality_issues.get(issue_id)
            if issue is None:
                return CustomerResult.fail("El problema de calidad no existe", "NOT_FOUND",
                                           operation_id=operation_id)
            try:
                issue.correct()
            except CustomerDomainError as exc:
                return CustomerResult.fail(str(exc), "VALIDATION", operation_id=operation_id)
            uow.data_quality_issues.update(issue)
            uow.audit.record(action=CustomerEvents.DATA_QUALITY_ISSUE_CORRECTED,
                             actor_user_id=actor_user_id, customer_id=issue.customer_id,
                             operation_id=operation_id,
                             after_json=json.dumps({"issue_id": issue.id}))
            self._emit(uow, CustomerEvents.DATA_QUALITY_ISSUE_CORRECTED, issue.customer_id,
                      operation_id, actor_user_id, issue_id=issue.id)
        return CustomerResult.ok("Problema corregido", entity_id=issue.id,
                                 operation_id=operation_id)


class DismissDataQualityIssueUseCase(_BaseUseCase):
    def execute(self, connection, *, actor_user_id: str, issue_id: str, reason: str,
                operation_id: str) -> CustomerResult:
        try:
            self._auth.require(actor_user_id, CustomerPermissions.DATA_QUALITY_RESOLVE)
        except CustomerDomainError as exc:
            return CustomerResult.fail(str(exc), "PERMISSION_DENIED", operation_id=operation_id)
        with CustomerUnitOfWork(connection) as uow:
            issue = uow.data_quality_issues.get(issue_id)
            if issue is None:
                return CustomerResult.fail("El problema de calidad no existe", "NOT_FOUND",
                                           operation_id=operation_id)
            try:
                issue.dismiss(actor_user_id, reason)
            except CustomerDomainError as exc:
                return CustomerResult.fail(str(exc), "VALIDATION", operation_id=operation_id)
            uow.data_quality_issues.update(issue)
            uow.audit.record(action=CustomerEvents.DATA_QUALITY_ISSUE_DISMISSED,
                             actor_user_id=actor_user_id, customer_id=issue.customer_id,
                             reason=reason, operation_id=operation_id,
                             after_json=json.dumps({"issue_id": issue.id}))
            self._emit(uow, CustomerEvents.DATA_QUALITY_ISSUE_DISMISSED, issue.customer_id,
                      operation_id, actor_user_id, issue_id=issue.id)
        return CustomerResult.ok("Problema descartado", entity_id=issue.id,
                                 operation_id=operation_id)
