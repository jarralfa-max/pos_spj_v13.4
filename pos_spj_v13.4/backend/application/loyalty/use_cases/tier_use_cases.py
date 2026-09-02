"""LOY-7 — Tier use cases: define tiers, evaluate a membership against them
(master prompt §14, phase list "LOY-7 — Niveles": Reglas, Evaluación,
Historial, Beneficios).

`EvaluateLoyaltyMembershipTierUseCase` is the only real consumer of
`LoyaltyMembership.change_tier()` (built in LOY-2, unused until now) — every
tier change writes a `LoyaltyTierHistory` row in the SAME transaction,
satisfying §14's "toda modificación de nivel debe dejar historial"
literally (there is no code path that calls `change_tier()` without also
recording history, since only this use case ever calls it).
"""

from __future__ import annotations

from decimal import Decimal

from backend.application.loyalty.dto import LoyaltyTierDTO
from backend.application.loyalty.permissions import LoyaltyPermissions
from backend.application.loyalty.result import LoyaltyResult, fail_from_domain_error
from backend.application.loyalty.use_cases._base import _LoyaltyBaseUseCase
from backend.domain.loyalty.entities.loyalty_tier import LoyaltyTier
from backend.domain.loyalty.entities.loyalty_tier_history import LoyaltyTierHistory
from backend.domain.loyalty.enums import TierEvaluationMethod
from backend.domain.loyalty.events import SYSTEM_ACTOR_ID, LoyaltyEvents
from backend.domain.loyalty.exceptions import (
    LoyaltyDomainError,
    LoyaltyMembershipNotFoundError,
    LoyaltyProgramNotFoundError,
)
from backend.domain.loyalty.policies.balance_policy import LoyaltyBalancePolicy
from backend.domain.loyalty.policies.tier_evaluation_policy import (
    LoyaltyTierEvaluationPolicy,
    TierEvaluationStats,
)
from backend.infrastructure.db.repositories.loyalty.unit_of_work import LoyaltyUnitOfWork


class CreateLoyaltyTierUseCase(_LoyaltyBaseUseCase):
    def execute(
        self, connection, *, program_id: str, code: str, name: str, rank: int,
        actor_user_id: str, operation_id: str, minimum_points: Decimal = Decimal("0"),
        minimum_spend: Decimal = Decimal("0"), minimum_visits: int = 0,
        evaluation_method: TierEvaluationMethod = TierEvaluationMethod.LIFETIME,
        benefit_multiplier: Decimal = Decimal("1"),
    ) -> LoyaltyResult:
        try:
            self._auth.require(actor_user_id, LoyaltyPermissions.TIER_MANAGE)
        except LoyaltyDomainError as exc:
            return fail_from_domain_error(exc, operation_id=operation_id)
        with LoyaltyUnitOfWork(connection) as uow:
            if uow.programs.get(program_id) is None:
                return fail_from_domain_error(
                    LoyaltyProgramNotFoundError(f"Programa {program_id} no existe"),
                    operation_id=operation_id)
            try:
                tier = LoyaltyTier.create(
                    program_id, code, name, rank, minimum_points=minimum_points,
                    minimum_spend=minimum_spend, minimum_visits=minimum_visits,
                    evaluation_method=evaluation_method,
                    benefit_multiplier=benefit_multiplier)
            except LoyaltyDomainError as exc:
                return fail_from_domain_error(exc, operation_id=operation_id)
            uow.tiers.save(tier)
        return LoyaltyResult.ok("Nivel creado", entity_id=tier.id, operation_id=operation_id,
                                tier=LoyaltyTierDTO.from_entity(tier))


class EvaluateLoyaltyMembershipTierUseCase(_LoyaltyBaseUseCase):
    """System-triggered evaluation (mirrors `ExpireLoyaltyPointsUseCase`'s
    own shape) — no `actor_user_id`/permission gate, since a tier
    recalculation is a derived fact, not a user-initiated command. Uses
    `SYSTEM_ACTOR_ID` for the emitted event, same reasoning as the
    expiration sweep."""

    def execute(
        self, connection, *, membership_id: str, actor_branch_id: str, operation_id: str,
        total_spend: Decimal = Decimal("0"), visit_count: int = 0,
    ) -> LoyaltyResult:
        with LoyaltyUnitOfWork(connection) as uow:
            membership = uow.memberships.get(membership_id)
            if membership is None:
                return fail_from_domain_error(
                    LoyaltyMembershipNotFoundError(f"Membresía {membership_id} no existe"),
                    operation_id=operation_id)
            tiers = uow.tiers.list_active_for_program(membership.program_id)
            if not tiers:
                return LoyaltyResult.ok(
                    "Sin niveles configurados", entity_id=membership.id,
                    operation_id=operation_id, tier=None)

            ledger = uow.transactions.list_for_account(membership.loyalty_account_id)
            lifetime_points = LoyaltyBalancePolicy.lifetime_earned(ledger)
            stats = TierEvaluationStats(
                lifetime_points=lifetime_points, total_spend=total_spend,
                visit_count=visit_count)
            new_tier = LoyaltyTierEvaluationPolicy.evaluate(tiers, stats)
            new_tier_id = new_tier.id if new_tier else None

            if new_tier_id == membership.current_tier_id:
                return LoyaltyResult.ok(
                    "Sin cambio de nivel", entity_id=membership.id,
                    operation_id=operation_id,
                    tier=LoyaltyTierDTO.from_entity(new_tier) if new_tier else None)

            previous_tier_id = membership.current_tier_id
            membership.change_tier(new_tier_id)
            uow.memberships.save(membership)
            history = LoyaltyTierHistory.record(
                membership.id, previous_tier_id=previous_tier_id, new_tier_id=new_tier_id,
                reason="Evaluación automática de nivel")
            uow.tier_history.add(history)
            self._emit(uow, LoyaltyEvents.TIER_CHANGED, entity_id=membership.id,
                       operation_id=operation_id, branch_id=actor_branch_id,
                       actor_user_id=SYSTEM_ACTOR_ID, previous_tier_id=previous_tier_id,
                       new_tier_id=new_tier_id)
        return LoyaltyResult.ok(
            "Nivel actualizado", entity_id=membership.id, operation_id=operation_id,
            tier=LoyaltyTierDTO.from_entity(new_tier) if new_tier else None)
