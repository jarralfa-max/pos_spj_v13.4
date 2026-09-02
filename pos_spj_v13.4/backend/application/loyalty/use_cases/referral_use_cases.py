"""LOY-10 — Referral use cases: Register, Qualify, Reward, Reject/Flag fraud
(master prompt §17, phase list "LOY-10 — Referidos": Registro,
Calificación, Recompensa, Antifraude).
"""

from __future__ import annotations

from decimal import Decimal

from backend.application.loyalty.dto import ReferralDTO
from backend.application.loyalty.permissions import LoyaltyPermissions
from backend.application.loyalty.result import LoyaltyResult, fail_from_domain_error
from backend.application.loyalty.use_cases._base import _LoyaltyBaseUseCase
from backend.domain.loyalty.entities.loyalty_transaction import LoyaltyTransaction
from backend.domain.loyalty.entities.referral import Referral
from backend.domain.loyalty.enums import TransactionType
from backend.domain.loyalty.events import LoyaltyEvents
from backend.domain.loyalty.exceptions import (
    LoyaltyDomainError,
    LoyaltyMembershipNotFoundError,
    ReferralNotFoundError,
    SelfReferralNotAllowedError,
)
from backend.infrastructure.db.repositories.loyalty.unit_of_work import LoyaltyUnitOfWork


class RegisterReferralUseCase(_LoyaltyBaseUseCase):
    def execute(
        self, connection, *, program_id: str, referrer_membership_id: str,
        referred_customer_id: str, referrer_bonus_points: Decimal, actor_user_id: str,
        operation_id: str, referred_bonus_points: Decimal = Decimal("0"),
        minimum_purchase_amount: Decimal = Decimal("0"), expires_at: str | None = None,
    ) -> LoyaltyResult:
        try:
            self._auth.require(actor_user_id, LoyaltyPermissions.REFERRAL_MANAGE)
        except LoyaltyDomainError as exc:
            return fail_from_domain_error(exc, operation_id=operation_id)
        with LoyaltyUnitOfWork(connection) as uow:
            referrer = uow.memberships.get(referrer_membership_id)
            if referrer is None:
                return fail_from_domain_error(
                    LoyaltyMembershipNotFoundError(
                        f"Membresía {referrer_membership_id} no existe"),
                    operation_id=operation_id)
            referrer_account = uow.accounts.get(referrer.loyalty_account_id)
            if referrer_account is not None and referrer_account.customer_id == referred_customer_id:
                return fail_from_domain_error(
                    SelfReferralNotAllowedError(
                        "El referidor y el referido no pueden ser el mismo cliente"),
                    operation_id=operation_id)
            try:
                referral = Referral.register(
                    program_id, referrer_membership_id, referred_customer_id,
                    referrer_bonus_points=referrer_bonus_points,
                    referred_bonus_points=referred_bonus_points,
                    minimum_purchase_amount=minimum_purchase_amount, expires_at=expires_at,
                )
            except LoyaltyDomainError as exc:
                return fail_from_domain_error(exc, operation_id=operation_id)
            uow.referrals.save(referral)
        return LoyaltyResult.ok(
            "Referido registrado", entity_id=referral.id, operation_id=operation_id,
            referral=ReferralDTO.from_entity(referral))


class _ReferralTransitionUseCase(_LoyaltyBaseUseCase):
    permission_code: str = ""
    event_name: str | None = None
    success_message: str = ""

    def _transition(self, referral: Referral, **kwargs) -> None:
        raise NotImplementedError

    def execute(self, connection, *, referral_id: str, actor_user_id: str,
                actor_branch_id: str, operation_id: str, **kwargs) -> LoyaltyResult:
        try:
            self._auth.require(actor_user_id, self.permission_code)
        except LoyaltyDomainError as exc:
            return fail_from_domain_error(exc, operation_id=operation_id)
        with LoyaltyUnitOfWork(connection) as uow:
            referral = uow.referrals.get(referral_id)
            if referral is None:
                return fail_from_domain_error(
                    ReferralNotFoundError(f"Referido {referral_id} no existe"),
                    operation_id=operation_id)
            try:
                self._transition(referral, uow=uow, actor_branch_id=actor_branch_id,
                                  actor_user_id=actor_user_id, operation_id=operation_id,
                                  **kwargs)
            except LoyaltyDomainError as exc:
                return fail_from_domain_error(exc, operation_id=operation_id)
            uow.referrals.save(referral)
            if self.event_name is not None:
                self._emit(uow, self.event_name, entity_id=referral.id,
                           operation_id=operation_id, branch_id=actor_branch_id,
                           actor_user_id=actor_user_id)
        return LoyaltyResult.ok(self.success_message, entity_id=referral.id,
                                operation_id=operation_id,
                                referral=ReferralDTO.from_entity(referral))


class QualifyReferralUseCase(_ReferralTransitionUseCase):
    permission_code = LoyaltyPermissions.REFERRAL_MANAGE
    success_message = "Referido calificado"

    def _transition(self, referral: Referral, **_kwargs) -> None:
        referral.qualify()


class RewardReferralUseCase(_ReferralTransitionUseCase):
    """Approving a referral's reward is a distinct permission
    (`REFERRAL_APPROVE`) from managing it (`REFERRAL_MANAGE`) — pays the
    referrer's bonus via a real `BONUS` ledger transaction, idempotency-
    guarded the same way LOY-9's challenge completion is (check + the
    schema's own real UNIQUE constraint)."""

    permission_code = LoyaltyPermissions.REFERRAL_APPROVE
    event_name = LoyaltyEvents.REFERRAL_QUALIFIED
    success_message = "Referido recompensado"

    def _transition(self, referral: Referral, *, uow, actor_branch_id: str,
                     actor_user_id: str, operation_id: str) -> None:
        referral.reward()
        referrer = uow.memberships.get(referral.referrer_membership_id)
        already_paid = uow.transactions.exists_for_source(
            source_module="loyalty_referrals", source_document_id=referral.id,
            transaction_type=TransactionType.BONUS, reason_code="REFERRAL_REWARD",
        )
        if not already_paid and referral.referrer_bonus_points > 0:
            bonus = LoyaltyTransaction.bonus(
                loyalty_account_id=referrer.loyalty_account_id,
                points_amount=referral.referrer_bonus_points, operation_id=operation_id,
                membership_id=referrer.id, source_module="loyalty_referrals",
                source_document_id=referral.id, reason_code="REFERRAL_REWARD",
                branch_id=actor_branch_id, created_by_user_id=actor_user_id,
            )
            uow.transactions.save(bonus)


class RejectReferralUseCase(_ReferralTransitionUseCase):
    permission_code = LoyaltyPermissions.REFERRAL_MANAGE
    success_message = "Referido rechazado"

    def execute(self, connection, *, referral_id: str, reason: str, actor_user_id: str,
                actor_branch_id: str, operation_id: str) -> LoyaltyResult:
        return super().execute(
            connection, referral_id=referral_id, actor_user_id=actor_user_id,
            actor_branch_id=actor_branch_id, operation_id=operation_id, reason=reason)

    def _transition(self, referral: Referral, *, reason: str, **_kwargs) -> None:
        referral.reject(reason)


class FlagReferralFraudSuspectedUseCase(_ReferralTransitionUseCase):
    permission_code = LoyaltyPermissions.REFERRAL_MANAGE
    success_message = "Referido marcado como sospechoso"

    def execute(self, connection, *, referral_id: str, reason: str, actor_user_id: str,
                actor_branch_id: str, operation_id: str) -> LoyaltyResult:
        return super().execute(
            connection, referral_id=referral_id, actor_user_id=actor_user_id,
            actor_branch_id=actor_branch_id, operation_id=operation_id, reason=reason)

    def _transition(self, referral: Referral, *, reason: str, **_kwargs) -> None:
        referral.flag_fraud_suspected(reason)
