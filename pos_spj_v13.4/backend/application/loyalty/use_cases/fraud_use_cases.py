"""LOY-26 — Fraud case use cases (master prompt §29).

``OpenFraudCaseUseCase`` accepts callers from ANYWHERE a suspicion
surfaces — a human reviewer flagging a pattern by hand, or a future
automated detector — so it is gated on `FRAUD_MANAGE` like every other
write here, never system-triggered-without-a-gate the way LOY-6/9/14's own
sweeps are: opening a case is itself a reportable action with a real actor,
unlike a scheduled expiration sweep.
"""

from __future__ import annotations

from backend.application.loyalty.permissions import LoyaltyPermissions
from backend.application.loyalty.result import LoyaltyResult, fail_from_domain_error
from backend.application.loyalty.use_cases._base import _LoyaltyBaseUseCase
from backend.domain.loyalty.entities.fraud_case import FraudCase
from backend.domain.loyalty.enums import FraudCaseSubjectType
from backend.domain.loyalty.events import LoyaltyEvents
from backend.domain.loyalty.exceptions import FraudCaseNotFoundError, LoyaltyDomainError
from backend.infrastructure.db.repositories.loyalty.unit_of_work import LoyaltyUnitOfWork


class OpenFraudCaseUseCase(_LoyaltyBaseUseCase):
    def execute(
        self, connection, *, subject_type: FraudCaseSubjectType, subject_id: str,
        customer_id: str, reason: str, actor_user_id: str, actor_branch_id: str,
        operation_id: str,
    ) -> LoyaltyResult:
        try:
            self._auth.require(actor_user_id, LoyaltyPermissions.FRAUD_MANAGE)
        except LoyaltyDomainError as exc:
            return fail_from_domain_error(exc, operation_id=operation_id)
        with LoyaltyUnitOfWork(connection) as uow:
            try:
                case = FraudCase.open(
                    subject_type, subject_id, customer_id, reason,
                    opened_by_user_id=actor_user_id)
            except LoyaltyDomainError as exc:
                return fail_from_domain_error(exc, operation_id=operation_id)
            uow.fraud_cases.save(case)
            self._emit(uow, LoyaltyEvents.FRAUD_CASE_OPENED, entity_id=case.id,
                       operation_id=operation_id, branch_id=actor_branch_id,
                       actor_user_id=actor_user_id, subject_type=subject_type.value,
                       subject_id=subject_id, customer_id=customer_id)
        return LoyaltyResult.ok("Caso de fraude abierto", entity_id=case.id,
                                operation_id=operation_id)


class StartFraudCaseReviewUseCase(_LoyaltyBaseUseCase):
    def execute(self, connection, *, case_id: str, actor_user_id: str, actor_branch_id: str,
                operation_id: str) -> LoyaltyResult:
        try:
            self._auth.require(actor_user_id, LoyaltyPermissions.FRAUD_MANAGE)
        except LoyaltyDomainError as exc:
            return fail_from_domain_error(exc, operation_id=operation_id)
        with LoyaltyUnitOfWork(connection) as uow:
            case = uow.fraud_cases.get(case_id)
            if case is None:
                return fail_from_domain_error(
                    FraudCaseNotFoundError(f"Caso {case_id} no existe"),
                    operation_id=operation_id)
            try:
                case.start_review(actor_user_id)
            except LoyaltyDomainError as exc:
                return fail_from_domain_error(exc, operation_id=operation_id)
            uow.fraud_cases.save(case)
        return LoyaltyResult.ok("Revisión de caso iniciada", entity_id=case.id,
                                operation_id=operation_id)


class ConfirmFraudCaseUseCase(_LoyaltyBaseUseCase):
    def execute(self, connection, *, case_id: str, resolution_notes: str, actor_user_id: str,
                actor_branch_id: str, operation_id: str) -> LoyaltyResult:
        try:
            self._auth.require(actor_user_id, LoyaltyPermissions.FRAUD_MANAGE)
        except LoyaltyDomainError as exc:
            return fail_from_domain_error(exc, operation_id=operation_id)
        with LoyaltyUnitOfWork(connection) as uow:
            case = uow.fraud_cases.get(case_id)
            if case is None:
                return fail_from_domain_error(
                    FraudCaseNotFoundError(f"Caso {case_id} no existe"),
                    operation_id=operation_id)
            try:
                case.confirm(resolution_notes)
            except LoyaltyDomainError as exc:
                return fail_from_domain_error(exc, operation_id=operation_id)
            uow.fraud_cases.save(case)
            self._emit(uow, LoyaltyEvents.FRAUD_CASE_CONFIRMED, entity_id=case.id,
                       operation_id=operation_id, branch_id=actor_branch_id,
                       actor_user_id=actor_user_id, subject_type=case.subject_type.value,
                       subject_id=case.subject_id, customer_id=case.customer_id)
        return LoyaltyResult.ok("Caso de fraude confirmado", entity_id=case.id,
                                operation_id=operation_id)


class DismissFraudCaseUseCase(_LoyaltyBaseUseCase):
    def execute(self, connection, *, case_id: str, resolution_notes: str, actor_user_id: str,
                actor_branch_id: str, operation_id: str) -> LoyaltyResult:
        try:
            self._auth.require(actor_user_id, LoyaltyPermissions.FRAUD_MANAGE)
        except LoyaltyDomainError as exc:
            return fail_from_domain_error(exc, operation_id=operation_id)
        with LoyaltyUnitOfWork(connection) as uow:
            case = uow.fraud_cases.get(case_id)
            if case is None:
                return fail_from_domain_error(
                    FraudCaseNotFoundError(f"Caso {case_id} no existe"),
                    operation_id=operation_id)
            try:
                case.dismiss(resolution_notes)
            except LoyaltyDomainError as exc:
                return fail_from_domain_error(exc, operation_id=operation_id)
            uow.fraud_cases.save(case)
            self._emit(uow, LoyaltyEvents.FRAUD_CASE_DISMISSED, entity_id=case.id,
                       operation_id=operation_id, branch_id=actor_branch_id,
                       actor_user_id=actor_user_id)
        return LoyaltyResult.ok("Caso de fraude descartado", entity_id=case.id,
                                operation_id=operation_id)
