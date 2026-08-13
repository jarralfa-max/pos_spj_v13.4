"""Customer duplicate-candidate use cases: detect, review, confirm, dismiss
(§45).

DetectDuplicateCandidatesUseCase runs the existing
``CustomerDuplicatePolicy.find_matches()`` (already used by
CreateCustomerUseCase/ConvertLeadUseCase for prevent-on-create) across the
whole customer base and persists each new match as a reviewable
CustomerDuplicateCandidate — the policy itself still never persists
anything (see its own docstring). Re-running detection is safe: pairs that
already have a non-terminal candidate are skipped
(``get_active_pair``), so it never creates duplicate duplicate-records.

Gated by DUPLICATES_VIEW, not DUPLICATES_REVIEW: running a scan is a
read/refresh action (nothing about a specific candidate is being decided
yet), same reasoning as CRM-10's query services treating "ver" as covering
its own refresh. The actual per-candidate decisions (review/confirm/
dismiss) are separate use cases below, gated by DUPLICATES_REVIEW/
DUPLICATES_DISMISS.
"""

from __future__ import annotations

import json

from backend.application.customers.authorization import CustomerAuthorizationPolicy
from backend.application.customers.permissions import CustomerPermissions
from backend.application.customers.result import CustomerResult
from backend.domain.customers.entities.customer_duplicate_candidate import (
    CustomerDuplicateCandidate,
)
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


class DetectDuplicateCandidatesUseCase(_BaseUseCase):
    def __init__(self, authorization: CustomerAuthorizationPolicy | None = None) -> None:
        super().__init__(authorization)
        self._policy = CustomerDuplicatePolicy()

    def execute(self, connection, *, actor_user_id: str, operation_id: str) -> CustomerResult:
        try:
            self._auth.require(actor_user_id, CustomerPermissions.DUPLICATES_VIEW)
        except CustomerDomainError as exc:
            return CustomerResult.fail(str(exc), "PERMISSION_DENIED", operation_id=operation_id)
        with CustomerUnitOfWork(connection) as uow:
            rows = uow.customers.find_duplicate_rows()
            detected_ids: list[str] = []
            for i, row in enumerate(rows):
                candidate_dict = {
                    "tax_identifier": row.get("tax_identifier"),
                    "display_name": row.get("display_name"), "legal_name": row.get("legal_name"),
                    "phone_e164": row.get("phone_e164"), "email": row.get("email"),
                }
                for match in self._policy.find_matches(candidate_dict, rows[i + 1:]):
                    pair_a, pair_b = row["id"], match.customer_id
                    if uow.duplicate_candidates.get_active_pair(pair_a, pair_b) is not None:
                        continue
                    pair_operation_id = f"{operation_id}:{pair_a}:{pair_b}"
                    candidate = CustomerDuplicateCandidate.detect(
                        pair_a, pair_b, match.reasons, operation_id=pair_operation_id)
                    uow.duplicate_candidates.save(candidate)
                    uow.audit.record(
                        action=CustomerEvents.DUPLICATE_DETECTED, actor_user_id=actor_user_id,
                        customer_id=pair_a, reason="; ".join(match.reasons),
                        after_json=json.dumps({"candidate_id": candidate.id,
                                               "customer_id_b": pair_b}),
                        operation_id=pair_operation_id)
                    self._emit(uow, CustomerEvents.DUPLICATE_DETECTED, pair_a,
                              pair_operation_id, actor_user_id, candidate_id=candidate.id,
                              customer_id_b=pair_b)
                    detected_ids.append(candidate.id)
        return CustomerResult.ok(
            f"{len(detected_ids)} candidato(s) de duplicado detectado(s)",
            operation_id=operation_id, candidate_ids=detected_ids)


class ReviewDuplicateCandidateUseCase(_BaseUseCase):
    def execute(self, connection, *, actor_user_id: str, candidate_id: str,
                operation_id: str) -> CustomerResult:
        try:
            self._auth.require(actor_user_id, CustomerPermissions.DUPLICATES_REVIEW)
        except CustomerDomainError as exc:
            return CustomerResult.fail(str(exc), "PERMISSION_DENIED", operation_id=operation_id)
        with CustomerUnitOfWork(connection) as uow:
            candidate = uow.duplicate_candidates.get(candidate_id)
            if candidate is None:
                return CustomerResult.fail("El candidato de duplicado no existe", "NOT_FOUND",
                                           operation_id=operation_id)
            try:
                candidate.start_review(actor_user_id)
            except CustomerDomainError as exc:
                return CustomerResult.fail(str(exc), "VALIDATION", operation_id=operation_id)
            uow.duplicate_candidates.update(candidate)
            uow.audit.record(action=CustomerEvents.DUPLICATE_UNDER_REVIEW,
                             actor_user_id=actor_user_id, customer_id=candidate.customer_id_a,
                             operation_id=operation_id,
                             after_json=json.dumps({"candidate_id": candidate.id}))
            self._emit(uow, CustomerEvents.DUPLICATE_UNDER_REVIEW, candidate.customer_id_a,
                      operation_id, actor_user_id, candidate_id=candidate.id)
        return CustomerResult.ok("Candidato en revisión", entity_id=candidate.id,
                                 operation_id=operation_id)


class ConfirmDuplicateCandidateUseCase(_BaseUseCase):
    def execute(self, connection, *, actor_user_id: str, candidate_id: str,
                operation_id: str) -> CustomerResult:
        try:
            self._auth.require(actor_user_id, CustomerPermissions.DUPLICATES_REVIEW)
        except CustomerDomainError as exc:
            return CustomerResult.fail(str(exc), "PERMISSION_DENIED", operation_id=operation_id)
        with CustomerUnitOfWork(connection) as uow:
            candidate = uow.duplicate_candidates.get(candidate_id)
            if candidate is None:
                return CustomerResult.fail("El candidato de duplicado no existe", "NOT_FOUND",
                                           operation_id=operation_id)
            try:
                candidate.confirm()
            except CustomerDomainError as exc:
                return CustomerResult.fail(str(exc), "VALIDATION", operation_id=operation_id)
            uow.duplicate_candidates.update(candidate)
            uow.audit.record(action=CustomerEvents.DUPLICATE_CONFIRMED,
                             actor_user_id=actor_user_id, customer_id=candidate.customer_id_a,
                             operation_id=operation_id,
                             after_json=json.dumps({"candidate_id": candidate.id}))
            self._emit(uow, CustomerEvents.DUPLICATE_CONFIRMED, candidate.customer_id_a,
                      operation_id, actor_user_id, candidate_id=candidate.id)
        return CustomerResult.ok("Duplicado confirmado", entity_id=candidate.id,
                                 operation_id=operation_id)


class DismissDuplicateCandidateUseCase(_BaseUseCase):
    def execute(self, connection, *, actor_user_id: str, candidate_id: str, reason: str,
                operation_id: str) -> CustomerResult:
        try:
            self._auth.require(actor_user_id, CustomerPermissions.DUPLICATES_DISMISS)
        except CustomerDomainError as exc:
            return CustomerResult.fail(str(exc), "PERMISSION_DENIED", operation_id=operation_id)
        with CustomerUnitOfWork(connection) as uow:
            candidate = uow.duplicate_candidates.get(candidate_id)
            if candidate is None:
                return CustomerResult.fail("El candidato de duplicado no existe", "NOT_FOUND",
                                           operation_id=operation_id)
            try:
                candidate.dismiss(reason)
            except CustomerDomainError as exc:
                return CustomerResult.fail(str(exc), "VALIDATION", operation_id=operation_id)
            uow.duplicate_candidates.update(candidate)
            uow.audit.record(action=CustomerEvents.DUPLICATE_DISMISSED,
                             actor_user_id=actor_user_id, customer_id=candidate.customer_id_a,
                             reason=reason, operation_id=operation_id,
                             after_json=json.dumps({"candidate_id": candidate.id}))
            self._emit(uow, CustomerEvents.DUPLICATE_DISMISSED, candidate.customer_id_a,
                      operation_id, actor_user_id, candidate_id=candidate.id)
        return CustomerResult.ok("Candidato descartado", entity_id=candidate.id,
                                 operation_id=operation_id)
