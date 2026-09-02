"""Sweepstakes winner validation/delivery use cases (LOY-15, master prompt
§27, §29 antifraude)."""

from __future__ import annotations

from backend.application.loyalty.permissions import LoyaltyPermissions
from backend.application.sweepstakes.result import SweepstakesResult, fail_from_domain_error
from backend.application.sweepstakes.use_cases._base import _SweepstakesBaseUseCase
from backend.domain.sweepstakes.entities.sweepstakes_winner import SweepstakesWinner
from backend.domain.sweepstakes.events import SweepstakesEvents
from backend.domain.sweepstakes.exceptions import (
    SweepstakesDomainError,
    SweepstakesPrizeNotFoundError,
    SweepstakesWinnerNotFoundError,
)
from backend.infrastructure.db.repositories.sweepstakes.unit_of_work import SweepstakesUnitOfWork


class _SweepstakesWinnerTransitionUseCase(_SweepstakesBaseUseCase):
    permission_code: str = LoyaltyPermissions.SWEEPSTAKES_MANAGE
    success_message: str = ""
    event_name: str | None = None

    def _transition(self, winner: SweepstakesWinner, **kwargs) -> None:
        raise NotImplementedError

    def execute(self, connection, *, winner_id: str, actor_user_id: str,
                operation_id: str, **kwargs) -> SweepstakesResult:
        try:
            self._auth.require(actor_user_id, self.permission_code)
            with SweepstakesUnitOfWork(connection) as uow:
                winner = uow.winners.get(winner_id)
                if winner is None:
                    return fail_from_domain_error(
                        SweepstakesWinnerNotFoundError(f"Ganador {winner_id} no existe"),
                        operation_id=operation_id)
                self._transition(winner, actor_user_id=actor_user_id, **kwargs)
                uow.winners.save(winner)
                if self.event_name is not None:
                    self._emit(uow, self.event_name, entity_id=winner.id,
                               operation_id=operation_id, branch_id=winner.customer_id,
                               actor_user_id=actor_user_id)
            return SweepstakesResult.ok(self.success_message, entity_id=winner.id,
                                         operation_id=operation_id)
        except SweepstakesDomainError as exc:
            return fail_from_domain_error(exc, operation_id=operation_id)


class ValidateSweepstakesWinnerUseCase(_SweepstakesWinnerTransitionUseCase):
    success_message = "Ganador validado"
    event_name = SweepstakesEvents.WINNER_VALIDATED

    def _transition(self, winner: SweepstakesWinner, *, actor_user_id: str) -> None:
        winner.validate(actor_user_id)


class DisqualifySweepstakesWinnerUseCase(_SweepstakesWinnerTransitionUseCase):
    success_message = "Ganador descalificado"
    event_name = SweepstakesEvents.WINNER_DISQUALIFIED

    def execute(self, connection, *, winner_id: str, reason: str, actor_user_id: str,
                operation_id: str) -> SweepstakesResult:
        return super().execute(connection, winner_id=winner_id, actor_user_id=actor_user_id,
                                operation_id=operation_id, reason=reason)

    def _transition(self, winner: SweepstakesWinner, *, reason: str, **_kwargs) -> None:
        winner.disqualify(reason)


class ExpireSweepstakesWinnerUseCase(_SweepstakesWinnerTransitionUseCase):
    success_message = "Premio no reclamado — vencido"

    def _transition(self, winner: SweepstakesWinner, **_kwargs) -> None:
        winner.expire()


class DeliverSweepstakesPrizeUseCase(_SweepstakesBaseUseCase):
    def execute(self, connection, *, winner_id: str, actor_user_id: str,
                operation_id: str) -> SweepstakesResult:
        try:
            self._auth.require(actor_user_id, LoyaltyPermissions.SWEEPSTAKES_MANAGE)
            with SweepstakesUnitOfWork(connection) as uow:
                winner = uow.winners.get(winner_id)
                if winner is None:
                    return fail_from_domain_error(
                        SweepstakesWinnerNotFoundError(f"Ganador {winner_id} no existe"),
                        operation_id=operation_id)
                prize = uow.prizes.get(winner.prize_id)
                if prize is None:
                    return fail_from_domain_error(
                        SweepstakesPrizeNotFoundError(f"Premio {winner.prize_id} no existe"),
                        operation_id=operation_id)
                winner.deliver_prize(actor_user_id)
                uow.winners.save(winner)
                prize.mark_delivered()
                uow.prizes.save(prize)
                self._emit(uow, SweepstakesEvents.PRIZE_DELIVERED, entity_id=winner.id,
                           operation_id=operation_id, branch_id=winner.customer_id,
                           actor_user_id=actor_user_id, prize_id=prize.id)
            return SweepstakesResult.ok("Premio entregado", entity_id=winner.id,
                                         operation_id=operation_id)
        except SweepstakesDomainError as exc:
            return fail_from_domain_error(exc, operation_id=operation_id)
