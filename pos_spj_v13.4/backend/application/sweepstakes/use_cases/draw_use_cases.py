"""Sweepstakes draw execution use cases (LOY-15, master prompt §27, §29
antifraude).

`ExecuteSweepstakesDrawUseCase` uses a SEEDED PRNG (`random.Random(seed)`),
not `secrets`/`SystemRandom` — a deliberate choice: the seed is generated
with `secrets.token_hex` (cryptographically unpredictable BEFORE the draw
runs) but the draw itself must be independently REPRODUCIBLE afterward for
audit (§29 antifraude: given the recorded `random_seed` and `pool_hash`, an
auditor must be able to re-run the exact same shuffle and get the exact
same winners) — `SystemRandom` alone would be unpredictable but not
auditable after the fact.
"""

from __future__ import annotations

import random
import secrets

from backend.application.loyalty.permissions import LoyaltyPermissions
from backend.application.sweepstakes.result import SweepstakesResult, fail_from_domain_error
from backend.application.sweepstakes.use_cases._base import _SweepstakesBaseUseCase
from backend.domain.sweepstakes.entities.sweepstakes_draw import SweepstakesDraw
from backend.domain.sweepstakes.entities.sweepstakes_winner import SweepstakesWinner
from backend.domain.sweepstakes.enums import SweepstakesCampaignStatus
from backend.domain.sweepstakes.events import SweepstakesEvents
from backend.domain.sweepstakes.exceptions import (
    DuplicateWinnerTicketError,
    SweepstakesCampaignNotFoundError,
    SweepstakesDomainError,
    SweepstakesDrawNotFoundError,
)
from backend.domain.sweepstakes.policies.draw_policy import SweepstakesDrawPolicy
from backend.infrastructure.db.repositories.sweepstakes.unit_of_work import SweepstakesUnitOfWork


class ScheduleSweepstakesDrawUseCase(_SweepstakesBaseUseCase):
    def execute(self, connection, *, campaign_id: str, actor_user_id: str, operation_id: str,
                scheduled_at: str | None = None) -> SweepstakesResult:
        try:
            self._auth.require(actor_user_id, LoyaltyPermissions.SWEEPSTAKES_DRAW)
            with SweepstakesUnitOfWork(connection) as uow:
                campaign = uow.campaigns.get(campaign_id)
                if campaign is None:
                    return fail_from_domain_error(
                        SweepstakesCampaignNotFoundError(f"Campaña {campaign_id} no existe"),
                        operation_id=operation_id)
                draw = SweepstakesDraw.schedule(campaign_id, scheduled_at=scheduled_at)
                uow.draws.save(draw)
                self._emit(uow, SweepstakesEvents.DRAW_SCHEDULED, entity_id=draw.id,
                           operation_id=operation_id, branch_id=campaign.branch_id or actor_user_id,
                           actor_user_id=actor_user_id)
            return SweepstakesResult.ok("Sorteo programado", entity_id=draw.id,
                                         operation_id=operation_id)
        except SweepstakesDomainError as exc:
            return fail_from_domain_error(exc, operation_id=operation_id)


class CancelSweepstakesDrawUseCase(_SweepstakesBaseUseCase):
    def execute(self, connection, *, draw_id: str, actor_user_id: str,
                operation_id: str) -> SweepstakesResult:
        try:
            self._auth.require(actor_user_id, LoyaltyPermissions.SWEEPSTAKES_DRAW)
            with SweepstakesUnitOfWork(connection) as uow:
                draw = uow.draws.get(draw_id)
                if draw is None:
                    return fail_from_domain_error(
                        SweepstakesDrawNotFoundError(f"Sorteo {draw_id} no existe"),
                        operation_id=operation_id)
                draw.cancel()
                uow.draws.save(draw)
                self._emit(uow, SweepstakesEvents.DRAW_CANCELLED, entity_id=draw.id,
                           operation_id=operation_id, branch_id=actor_user_id,
                           actor_user_id=actor_user_id)
            return SweepstakesResult.ok("Sorteo cancelado", entity_id=draw.id,
                                         operation_id=operation_id)
        except SweepstakesDomainError as exc:
            return fail_from_domain_error(exc, operation_id=operation_id)


class ExecuteSweepstakesDrawUseCase(_SweepstakesBaseUseCase):
    def execute(self, connection, *, draw_id: str, actor_user_id: str,
                operation_id: str) -> SweepstakesResult:
        try:
            self._auth.require(actor_user_id, LoyaltyPermissions.SWEEPSTAKES_DRAW)
            with SweepstakesUnitOfWork(connection) as uow:
                draw = uow.draws.get(draw_id)
                if draw is None:
                    return fail_from_domain_error(
                        SweepstakesDrawNotFoundError(f"Sorteo {draw_id} no existe"),
                        operation_id=operation_id)
                campaign = uow.campaigns.get(draw.campaign_id)
                if campaign is None:
                    return fail_from_domain_error(
                        SweepstakesCampaignNotFoundError(
                            f"Campaña {draw.campaign_id} no existe"),
                        operation_id=operation_id)

                all_tickets = uow.tickets.list_eligible_for_campaign(draw.campaign_id)
                already_won = uow.winners.list_ticket_ids_won_in_campaign(draw.campaign_id)
                pool = SweepstakesDrawPolicy.eligible_tickets(
                    all_tickets, exclude_ticket_ids=already_won)
                pool_hash = SweepstakesDrawPolicy.pool_hash(pool)

                draw.complete(
                    executed_by_user_id=actor_user_id, random_seed=secrets.token_hex(16),
                    pool_hash=pool_hash, ticket_pool_size=len(pool))
                uow.draws.save(draw)

                rng = random.Random(draw.random_seed)
                shuffled = list(pool)
                rng.shuffle(shuffled)

                prizes = uow.prizes.list_for_campaign(draw.campaign_id)
                winners: list[SweepstakesWinner] = []
                selected_ticket_ids: set[str] = set()
                cursor = 0
                overall_rank = 1
                for prize in prizes:
                    for _ in range(prize.quantity):
                        if cursor >= len(shuffled):
                            break
                        ticket = shuffled[cursor]
                        cursor += 1
                        if ticket.id in selected_ticket_ids:
                            raise DuplicateWinnerTicketError(
                                f"El boleto {ticket.id} ya fue seleccionado en este sorteo")
                        selected_ticket_ids.add(ticket.id)
                        winner = SweepstakesWinner.select(
                            draw.id, draw.campaign_id, ticket.id, ticket.customer_id, prize.id,
                            rank=overall_rank)
                        overall_rank += 1
                        uow.winners.save(winner)
                        winners.append(winner)
                        self._emit(uow, SweepstakesEvents.WINNER_SELECTED, entity_id=winner.id,
                                   operation_id=operation_id,
                                   branch_id=campaign.branch_id or actor_user_id,
                                   actor_user_id=actor_user_id, ticket_id=ticket.id,
                                   prize_id=prize.id)

                if campaign.status is not SweepstakesCampaignStatus.DRAWN:
                    # A campaign may run multiple draws (one per prize batch,
                    # e.g. a 2nd-place draw added after the 1st place draw
                    # already ran) — only the FIRST completed draw transitions
                    # the campaign DRAFT/ACTIVE→DRAWN; later draws leave it as-is.
                    campaign.mark_drawn()
                    uow.campaigns.save(campaign)
                self._emit(uow, SweepstakesEvents.DRAW_COMPLETED, entity_id=draw.id,
                           operation_id=operation_id, branch_id=campaign.branch_id or actor_user_id,
                           actor_user_id=actor_user_id, winners_count=len(winners),
                           pool_size=len(pool))
            return SweepstakesResult.ok(
                "Sorteo ejecutado", entity_id=draw.id, operation_id=operation_id,
                winners=[w.id for w in winners], pool_size=len(pool))
        except SweepstakesDomainError as exc:
            return fail_from_domain_error(exc, operation_id=operation_id)
