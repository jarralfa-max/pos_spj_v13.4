"""LOY-9 — Gamification use cases: define challenges, record progress,
record streak activity (master prompt §16, phase list "LOY-9 —
Gamificación": Retos, Misiones, Rachas, Progreso).

`RecordChallengeProgressUseCase` is the only real consumer of
`AccrueLoyaltyPointsUseCase`'s underlying mechanics for a NEW source module
(`loyalty_challenges`) — completing a challenge grants points via a `BONUS`
ledger transaction, idempotency-checked the same way LOY-6 checks sales
accrual (`exists_for_source`), so completing the same challenge twice for
the same membership never double-pays (master prompt §16: "No otorgar
puntos sin operación idempotente").
"""

from __future__ import annotations

from decimal import Decimal

from backend.application.loyalty.dto import ChallengeProgressDTO, LoyaltyChallengeDTO
from backend.application.loyalty.permissions import LoyaltyPermissions
from backend.application.loyalty.result import LoyaltyResult, fail_from_domain_error
from backend.application.loyalty.use_cases._base import _LoyaltyBaseUseCase
from backend.domain.loyalty.entities.challenge_progress import ChallengeProgress
from backend.domain.loyalty.entities.loyalty_badge import LoyaltyBadge
from backend.domain.loyalty.entities.loyalty_challenge import LoyaltyChallenge
from backend.domain.loyalty.entities.loyalty_streak import LoyaltyStreak
from backend.domain.loyalty.entities.loyalty_transaction import LoyaltyTransaction
from backend.domain.loyalty.enums import ChallengeCriteriaType, ChallengeMode, TransactionType
from backend.domain.loyalty.events import SYSTEM_ACTOR_ID, LoyaltyEvents
from backend.domain.loyalty.exceptions import (
    LoyaltyChallengeNotFoundError,
    LoyaltyDomainError,
    LoyaltyMembershipNotFoundError,
    LoyaltyProgramNotFoundError,
)
from backend.infrastructure.db.repositories.loyalty.unit_of_work import LoyaltyUnitOfWork


class CreateLoyaltyChallengeUseCase(_LoyaltyBaseUseCase):
    def execute(
        self, connection, *, program_id: str, code: str, name: str,
        criteria_type: ChallengeCriteriaType, target_value: Decimal, points_reward: Decimal,
        actor_user_id: str, operation_id: str, mode: ChallengeMode = ChallengeMode.CHALLENGE,
        description: str = "",
    ) -> LoyaltyResult:
        try:
            self._auth.require(actor_user_id, LoyaltyPermissions.CHALLENGE_MANAGE)
        except LoyaltyDomainError as exc:
            return fail_from_domain_error(exc, operation_id=operation_id)
        with LoyaltyUnitOfWork(connection) as uow:
            if uow.programs.get(program_id) is None:
                return fail_from_domain_error(
                    LoyaltyProgramNotFoundError(f"Programa {program_id} no existe"),
                    operation_id=operation_id)
            try:
                challenge = LoyaltyChallenge.create(
                    program_id, code, name, criteria_type, target_value, points_reward,
                    mode=mode, description=description)
            except LoyaltyDomainError as exc:
                return fail_from_domain_error(exc, operation_id=operation_id)
            uow.challenges.save(challenge)
        return LoyaltyResult.ok(
            "Reto creado", entity_id=challenge.id, operation_id=operation_id,
            challenge=LoyaltyChallengeDTO.from_entity(challenge))


class ActivateLoyaltyChallengeUseCase(_LoyaltyBaseUseCase):
    def execute(self, connection, *, challenge_id: str, actor_user_id: str,
                operation_id: str) -> LoyaltyResult:
        try:
            self._auth.require(actor_user_id, LoyaltyPermissions.CHALLENGE_MANAGE)
        except LoyaltyDomainError as exc:
            return fail_from_domain_error(exc, operation_id=operation_id)
        with LoyaltyUnitOfWork(connection) as uow:
            challenge = uow.challenges.get(challenge_id)
            if challenge is None:
                return fail_from_domain_error(
                    LoyaltyChallengeNotFoundError(f"Reto {challenge_id} no existe"),
                    operation_id=operation_id)
            try:
                challenge.activate()
            except LoyaltyDomainError as exc:
                return fail_from_domain_error(exc, operation_id=operation_id)
            uow.challenges.save(challenge)
        return LoyaltyResult.ok(
            "Reto activado", entity_id=challenge.id, operation_id=operation_id,
            challenge=LoyaltyChallengeDTO.from_entity(challenge))


class RecordChallengeProgressUseCase(_LoyaltyBaseUseCase):
    """System-triggered (mirrors LOY-6's `ExpireLoyaltyPointsUseCase`/LOY-7's
    tier evaluation) — progress advances in reaction to a real event (a
    sale, a referral) elsewhere in the system, not a direct user command, so
    there is no `actor_user_id`/permission gate here."""

    def execute(
        self, connection, *, challenge_id: str, membership_id: str, amount: Decimal,
        actor_branch_id: str, operation_id: str,
    ) -> LoyaltyResult:
        with LoyaltyUnitOfWork(connection) as uow:
            challenge = uow.challenges.get(challenge_id)
            if challenge is None:
                return fail_from_domain_error(
                    LoyaltyChallengeNotFoundError(f"Reto {challenge_id} no existe"),
                    operation_id=operation_id)
            if not challenge.is_active():
                return fail_from_domain_error(
                    LoyaltyDomainError(f"El reto {challenge.code} no está activo"),
                    operation_id=operation_id)
            membership = uow.memberships.get(membership_id)
            if membership is None:
                return fail_from_domain_error(
                    LoyaltyMembershipNotFoundError(f"Membresía {membership_id} no existe"),
                    operation_id=operation_id)

            progress = uow.challenge_progress.get_by_challenge_and_membership(
                challenge_id, membership_id)
            if progress is None:
                progress = ChallengeProgress.start(challenge_id, membership_id)
            try:
                progress.increment(amount)
            except LoyaltyDomainError as exc:
                return fail_from_domain_error(exc, operation_id=operation_id)

            just_completed = False
            if not progress.completed and progress.has_reached(challenge.target_value):
                already_paid = uow.transactions.exists_for_source(
                    source_module="loyalty_challenges", source_document_id=challenge_id,
                    transaction_type=TransactionType.BONUS,
                    reason_code=f"CHALLENGE:{membership_id}",
                )
                if not already_paid:
                    bonus = LoyaltyTransaction.bonus(
                        loyalty_account_id=membership.loyalty_account_id,
                        points_amount=challenge.points_reward, operation_id=operation_id,
                        membership_id=membership_id, source_module="loyalty_challenges",
                        source_document_id=challenge_id,
                        reason_code=f"CHALLENGE:{membership_id}",
                        branch_id=actor_branch_id, created_by_user_id=SYSTEM_ACTOR_ID,
                    )
                    uow.transactions.save(bonus)
                    badge = LoyaltyBadge.award(
                        membership_id, f"CHALLENGE_{challenge.code}",
                        source_challenge_id=challenge_id)
                    uow.badges.add(badge)
                    just_completed = True
                progress.mark_completed(challenge.points_reward)
            uow.challenge_progress.save(progress)
            if just_completed:
                self._emit(uow, LoyaltyEvents.CHALLENGE_COMPLETED, entity_id=progress.id,
                           operation_id=operation_id, branch_id=actor_branch_id,
                           actor_user_id=SYSTEM_ACTOR_ID, challenge_id=challenge_id,
                           membership_id=membership_id,
                           points_reward=str(challenge.points_reward))
        return LoyaltyResult.ok(
            "Progreso registrado", entity_id=progress.id, operation_id=operation_id,
            progress=ChallengeProgressDTO.from_entity(progress), completed=just_completed)


class RecordLoyaltyStreakActivityUseCase(_LoyaltyBaseUseCase):
    """System-triggered, same reasoning as `RecordChallengeProgressUseCase`."""

    def execute(
        self, connection, *, membership_id: str, streak_type: str, period: str,
        is_consecutive: bool,
    ) -> LoyaltyResult:
        with LoyaltyUnitOfWork(connection) as uow:
            streak = uow.streaks.get_by_membership_and_type(membership_id, streak_type)
            if streak is None:
                try:
                    streak = LoyaltyStreak.start(membership_id, streak_type)
                except LoyaltyDomainError as exc:
                    return fail_from_domain_error(exc, operation_id=period)
            streak.record_period(period, is_consecutive=is_consecutive)
            uow.streaks.save(streak)
        return LoyaltyResult.ok(
            "Racha actualizada", entity_id=streak.id,
            current_count=streak.current_count, longest_count=streak.longest_count)
