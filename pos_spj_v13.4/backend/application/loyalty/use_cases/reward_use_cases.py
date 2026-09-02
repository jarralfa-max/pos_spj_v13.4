"""LOY-8 — Reward use cases: Create, Request redemption, Confirm, Cancel
(master prompt §15, phase list "LOY-8 — Recompensas": Definición,
Elegibilidad, Reserva, Canje).

Redemption reuses LOY-6's own ledger machinery directly at the domain/policy
level (`LoyaltyTransaction.reserve()`/`.release_of()`, `LoyaltyBalancePolicy`)
rather than calling `ReserveLoyaltyPointsUseCase` as a whole — each use case
in this codebase owns exactly one `LoyaltyUnitOfWork` transaction, so
composing by nesting a second use case's own UoW would fight over the
commit boundary. This mirrors how SALES-9's `SuspendSaleUseCase` calls
`SalesInventoryClient` (an infrastructure client) rather than nesting a
whole second Sales use case for a sub-step.
"""

from __future__ import annotations

from decimal import Decimal

from backend.application.loyalty.dto import RewardDTO, RewardRedemptionDTO
from backend.application.loyalty.permissions import LoyaltyPermissions
from backend.application.loyalty.result import LoyaltyResult, fail_from_domain_error
from backend.application.loyalty.use_cases._base import _LoyaltyBaseUseCase
from backend.domain.loyalty.entities.loyalty_transaction import LoyaltyTransaction
from backend.domain.loyalty.entities.reward import Reward
from backend.domain.loyalty.entities.reward_redemption import RewardRedemption
from backend.domain.loyalty.enums import RewardType
from backend.domain.loyalty.events import LoyaltyEvents
from backend.domain.loyalty.exceptions import (
    InsufficientLoyaltyPointsError,
    LoyaltyDomainError,
    LoyaltyMembershipNotFoundError,
    LoyaltyProgramNotFoundError,
    RewardNotAvailableError,
    RewardNotFoundError,
    RewardRedemptionNotFoundError,
)
from backend.domain.loyalty.policies.balance_policy import LoyaltyBalancePolicy
from backend.infrastructure.db.repositories.loyalty.unit_of_work import LoyaltyUnitOfWork


class CreateRewardUseCase(_LoyaltyBaseUseCase):
    def execute(
        self, connection, *, program_id: str, code: str, name: str,
        reward_type: RewardType, points_cost: Decimal, actor_user_id: str,
        operation_id: str, description: str = "", value: Decimal = Decimal("0"),
    ) -> LoyaltyResult:
        try:
            self._auth.require(actor_user_id, LoyaltyPermissions.REWARD_MANAGE)
        except LoyaltyDomainError as exc:
            return fail_from_domain_error(exc, operation_id=operation_id)
        with LoyaltyUnitOfWork(connection) as uow:
            if uow.programs.get(program_id) is None:
                return fail_from_domain_error(
                    LoyaltyProgramNotFoundError(f"Programa {program_id} no existe"),
                    operation_id=operation_id)
            try:
                reward = Reward.create(program_id, code, name, reward_type, points_cost,
                                        description=description, value=value)
            except LoyaltyDomainError as exc:
                return fail_from_domain_error(exc, operation_id=operation_id)
            uow.rewards.save(reward)
        return LoyaltyResult.ok("Recompensa creada", entity_id=reward.id,
                                operation_id=operation_id, reward=RewardDTO.from_entity(reward))


class RequestRewardRedemptionUseCase(_LoyaltyBaseUseCase):
    def execute(
        self, connection, *, reward_id: str, membership_id: str, actor_user_id: str,
        actor_branch_id: str, operation_id: str, sale_id: str | None = None,
    ) -> LoyaltyResult:
        try:
            self._auth.require(actor_user_id, LoyaltyPermissions.REWARD_REDEEM)
        except LoyaltyDomainError as exc:
            return fail_from_domain_error(exc, operation_id=operation_id)
        with LoyaltyUnitOfWork(connection) as uow:
            reward = uow.rewards.get(reward_id)
            if reward is None:
                return fail_from_domain_error(
                    RewardNotFoundError(f"Recompensa {reward_id} no existe"),
                    operation_id=operation_id)
            if not reward.active:
                return fail_from_domain_error(
                    RewardNotAvailableError(f"La recompensa {reward.code} no está activa"),
                    operation_id=operation_id)
            membership = uow.memberships.get(membership_id)
            if membership is None:
                return fail_from_domain_error(
                    LoyaltyMembershipNotFoundError(f"Membresía {membership_id} no existe"),
                    operation_id=operation_id)
            if membership.program_id != reward.program_id:
                return fail_from_domain_error(
                    RewardNotAvailableError(
                        "La recompensa pertenece a otro programa de fidelidad"),
                    operation_id=operation_id)

            ledger = uow.transactions.list_for_account(membership.loyalty_account_id)
            balance = LoyaltyBalancePolicy.balance(ledger)
            if balance < reward.points_cost:
                return fail_from_domain_error(
                    InsufficientLoyaltyPointsError(
                        f"Saldo insuficiente: disponible {balance}, "
                        f"requerido {reward.points_cost}"),
                    operation_id=operation_id)

            reservation = LoyaltyTransaction.reserve(
                loyalty_account_id=membership.loyalty_account_id,
                points_amount=-reward.points_cost, operation_id=operation_id,
                membership_id=membership.id, source_module="loyalty_rewards",
                reason_code=f"REWARD:{reward.code}", sale_id=sale_id,
                branch_id=actor_branch_id, created_by_user_id=actor_user_id,
            )
            uow.transactions.save(reservation)
            redemption = RewardRedemption.request(
                reward.id, membership.id, membership.loyalty_account_id, reservation.id,
                sale_id=sale_id)
            uow.reward_redemptions.save(redemption)
            self._emit(uow, LoyaltyEvents.POINTS_RESERVED, entity_id=reservation.id,
                       operation_id=operation_id, branch_id=actor_branch_id,
                       actor_user_id=actor_user_id, reward_id=reward.id,
                       redemption_id=redemption.id, points_amount=str(reward.points_cost))
        return LoyaltyResult.ok(
            "Canje reservado", entity_id=redemption.id, operation_id=operation_id,
            redemption=RewardRedemptionDTO.from_entity(redemption))


class ConfirmRewardRedemptionUseCase(_LoyaltyBaseUseCase):
    def execute(self, connection, *, redemption_id: str, actor_user_id: str,
                actor_branch_id: str, operation_id: str) -> LoyaltyResult:
        try:
            self._auth.require(actor_user_id, LoyaltyPermissions.REWARD_REDEEM)
        except LoyaltyDomainError as exc:
            return fail_from_domain_error(exc, operation_id=operation_id)
        with LoyaltyUnitOfWork(connection) as uow:
            redemption = uow.reward_redemptions.get(redemption_id)
            if redemption is None:
                return fail_from_domain_error(
                    RewardRedemptionNotFoundError(f"Canje {redemption_id} no existe"),
                    operation_id=operation_id)
            reservation = uow.transactions.get(redemption.points_transaction_id)
            try:
                # Validate the redemption's OWN state first — it is the
                # concept the caller is acting on. Consuming the underlying
                # ledger reservation second means a stale/cancelled
                # redemption always fails with REWARD_REDEMPTION_INVALID_STATE,
                # never a confusing TRANSACTION_INVALID_STATE about an
                # implementation detail the caller doesn't know about.
                redemption.confirm()
                reservation.mark_consumed()
            except LoyaltyDomainError as exc:
                return fail_from_domain_error(exc, operation_id=operation_id)
            uow.transactions.save(reservation)
            uow.reward_redemptions.save(redemption)
            self._emit(uow, LoyaltyEvents.REWARD_GRANTED, entity_id=redemption.id,
                       operation_id=operation_id, branch_id=actor_branch_id,
                       actor_user_id=actor_user_id, reward_id=redemption.reward_id)
        return LoyaltyResult.ok(
            "Canje confirmado", entity_id=redemption.id, operation_id=operation_id,
            redemption=RewardRedemptionDTO.from_entity(redemption))


class CancelRewardRedemptionUseCase(_LoyaltyBaseUseCase):
    def execute(self, connection, *, redemption_id: str, actor_user_id: str,
                actor_branch_id: str, operation_id: str) -> LoyaltyResult:
        try:
            self._auth.require(actor_user_id, LoyaltyPermissions.REWARD_REDEEM)
        except LoyaltyDomainError as exc:
            return fail_from_domain_error(exc, operation_id=operation_id)
        with LoyaltyUnitOfWork(connection) as uow:
            redemption = uow.reward_redemptions.get(redemption_id)
            if redemption is None:
                return fail_from_domain_error(
                    RewardRedemptionNotFoundError(f"Canje {redemption_id} no existe"),
                    operation_id=operation_id)
            reservation = uow.transactions.get(redemption.points_transaction_id)
            try:
                # Same ordering discipline as ConfirmRewardRedemptionUseCase:
                # validate the redemption's own state before touching the
                # underlying ledger reservation.
                redemption.cancel()
                release = LoyaltyTransaction.release_of(
                    reservation, operation_id=operation_id, created_by_user_id=actor_user_id)
                reservation.cancel_reservation()
            except LoyaltyDomainError as exc:
                return fail_from_domain_error(exc, operation_id=operation_id)
            uow.transactions.save(reservation)
            uow.transactions.save(release)
            uow.reward_redemptions.save(redemption)
            self._emit(uow, LoyaltyEvents.POINTS_RELEASED, entity_id=release.id,
                       operation_id=operation_id, branch_id=actor_branch_id,
                       actor_user_id=actor_user_id, redemption_id=redemption.id)
        return LoyaltyResult.ok(
            "Canje cancelado", entity_id=redemption.id, operation_id=operation_id,
            redemption=RewardRedemptionDTO.from_entity(redemption))
