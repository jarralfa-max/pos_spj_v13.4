"""LOY-15 — Sweepstakes use cases (master prompt §27-28)."""

from __future__ import annotations

import sqlite3
from decimal import Decimal

import pytest

from backend.application.loyalty.authorization import LoyaltyAuthorizationPolicy
from backend.application.sweepstakes.use_cases.campaign_use_cases import (
    ActivateSweepstakesCampaignUseCase,
    AddSweepstakesPrizeUseCase,
    ApproveSweepstakesCampaignUseCase,
    CancelSweepstakesCampaignUseCase,
    CloseSweepstakesCampaignUseCase,
    ConfigureSweepstakesRuleUseCase,
    CreateSweepstakesCampaignUseCase,
    PauseSweepstakesCampaignUseCase,
    ResumeSweepstakesCampaignUseCase,
)
from backend.application.sweepstakes.use_cases.draw_use_cases import (
    CancelSweepstakesDrawUseCase,
    ExecuteSweepstakesDrawUseCase,
    ScheduleSweepstakesDrawUseCase,
)
from backend.application.sweepstakes.use_cases.entry_use_cases import (
    GrantSweepstakesEntryUseCase,
    IssueSweepstakesTicketUseCase,
    PrintSweepstakesTicketUseCase,
    VoidSweepstakesTicketUseCase,
)
from backend.application.sweepstakes.use_cases.winner_use_cases import (
    DeliverSweepstakesPrizeUseCase,
    DisqualifySweepstakesWinnerUseCase,
    ValidateSweepstakesWinnerUseCase,
)
from backend.domain.sweepstakes.enums import SweepstakesEntryMethod
from backend.infrastructure.db.schema.sweepstakes_schema import create_sweepstakes_schema
from backend.shared.ids import new_uuid


@pytest.fixture
def conn():
    c = sqlite3.connect(":memory:")
    c.execute("PRAGMA foreign_keys = ON")
    create_sweepstakes_schema(c)
    c.commit()
    yield c
    c.close()


@pytest.fixture
def auth():
    return LoyaltyAuthorizationPolicy.permissive_for_tests()


def _active_campaign(conn, auth, *, max_tickets_per_customer: int = 0):
    creator = new_uuid()
    create = CreateSweepstakesCampaignUseCase(auth).execute(
        conn, code="RIFA1", name="Rifa de verano", actor_user_id=creator,
        operation_id=new_uuid(), max_tickets_per_customer=max_tickets_per_customer)
    ApproveSweepstakesCampaignUseCase(auth).execute(
        conn, campaign_id=create.entity_id, actor_user_id=new_uuid(), operation_id=new_uuid())
    ActivateSweepstakesCampaignUseCase(auth).execute(
        conn, campaign_id=create.entity_id, actor_user_id=new_uuid(), operation_id=new_uuid())
    return create.entity_id


class TestCampaignLifecycle:
    def test_create_starts_pending_approval_then_activates(self, conn, auth):
        campaign_id = _active_campaign(conn, auth)
        assert campaign_id is not None

    def test_pause_and_resume(self, conn, auth):
        campaign_id = _active_campaign(conn, auth)
        result = PauseSweepstakesCampaignUseCase(auth).execute(
            conn, campaign_id=campaign_id, actor_user_id=new_uuid(), operation_id=new_uuid())
        assert result.success
        result = ResumeSweepstakesCampaignUseCase(auth).execute(
            conn, campaign_id=campaign_id, actor_user_id=new_uuid(), operation_id=new_uuid())
        assert result.success

    def test_cancel_from_active(self, conn, auth):
        campaign_id = _active_campaign(conn, auth)
        result = CancelSweepstakesCampaignUseCase(auth).execute(
            conn, campaign_id=campaign_id, actor_user_id=new_uuid(), operation_id=new_uuid())
        assert result.success

    def test_campaign_not_found(self, conn, auth):
        result = ApproveSweepstakesCampaignUseCase(auth).execute(
            conn, campaign_id=new_uuid(), actor_user_id=new_uuid(), operation_id=new_uuid())
        assert not result.success
        assert result.error_code == "CAMPAIGN_NOT_FOUND"


class TestRuleAndPrize:
    def test_configure_rule(self, conn, auth):
        campaign_id = _active_campaign(conn, auth)
        result = ConfigureSweepstakesRuleUseCase(auth).execute(
            conn, campaign_id=campaign_id, entry_method=SweepstakesEntryMethod.PURCHASE_AMOUNT,
            actor_user_id=new_uuid(), operation_id=new_uuid(), amount_per_ticket=Decimal("100"))
        assert result.success

    def test_add_prize(self, conn, auth):
        campaign_id = _active_campaign(conn, auth)
        result = AddSweepstakesPrizeUseCase(auth).execute(
            conn, campaign_id=campaign_id, name="Televisión", actor_user_id=new_uuid(),
            operation_id=new_uuid(), quantity=1, rank=1)
        assert result.success


class TestEntryAndTicketFlow:
    def test_ticket_requires_existing_entry(self, conn, auth):
        campaign_id = _active_campaign(conn, auth)
        result = IssueSweepstakesTicketUseCase(auth).execute(
            conn, campaign_id=campaign_id, entry_id=new_uuid(), actor_user_id=new_uuid(),
            operation_id=new_uuid())
        assert not result.success
        assert result.error_code == "ENTRY_NOT_FOUND"

    def test_grant_entry_then_issue_ticket(self, conn, auth):
        campaign_id = _active_campaign(conn, auth)
        customer_id = new_uuid()
        entry = GrantSweepstakesEntryUseCase(auth).execute(
            conn, campaign_id=campaign_id, customer_id=customer_id,
            entry_method=SweepstakesEntryMethod.MANUAL_GRANT, actor_user_id=new_uuid(),
            operation_id=new_uuid(), chances_granted=1)
        assert entry.success
        ticket = IssueSweepstakesTicketUseCase(auth).execute(
            conn, campaign_id=campaign_id, entry_id=entry.entity_id, actor_user_id=new_uuid(),
            operation_id=new_uuid())
        assert ticket.success
        assert ticket.data["ticket_number"] == "RIFA1-000001"

    def test_cannot_issue_more_tickets_than_chances(self, conn, auth):
        campaign_id = _active_campaign(conn, auth)
        entry = GrantSweepstakesEntryUseCase(auth).execute(
            conn, campaign_id=campaign_id, customer_id=new_uuid(),
            entry_method=SweepstakesEntryMethod.MANUAL_GRANT, actor_user_id=new_uuid(),
            operation_id=new_uuid(), chances_granted=1)
        IssueSweepstakesTicketUseCase(auth).execute(
            conn, campaign_id=campaign_id, entry_id=entry.entity_id, actor_user_id=new_uuid(),
            operation_id=new_uuid())
        result = IssueSweepstakesTicketUseCase(auth).execute(
            conn, campaign_id=campaign_id, entry_id=entry.entity_id, actor_user_id=new_uuid(),
            operation_id=new_uuid())
        assert not result.success
        assert result.error_code == "TICKET_REQUIRES_ENTRY"

    def test_customer_max_tickets_enforced(self, conn, auth):
        campaign_id = _active_campaign(conn, auth, max_tickets_per_customer=1)
        customer_id = new_uuid()
        entry1 = GrantSweepstakesEntryUseCase(auth).execute(
            conn, campaign_id=campaign_id, customer_id=customer_id,
            entry_method=SweepstakesEntryMethod.MANUAL_GRANT, actor_user_id=new_uuid(),
            operation_id=new_uuid(), chances_granted=2)
        IssueSweepstakesTicketUseCase(auth).execute(
            conn, campaign_id=campaign_id, entry_id=entry1.entity_id, actor_user_id=new_uuid(),
            operation_id=new_uuid())
        result = IssueSweepstakesTicketUseCase(auth).execute(
            conn, campaign_id=campaign_id, entry_id=entry1.entity_id, actor_user_id=new_uuid(),
            operation_id=new_uuid())
        assert not result.success
        assert result.error_code == "CAMPAIGN_INVALID_STATE"

    def test_print_then_reprint_ticket(self, conn, auth):
        campaign_id = _active_campaign(conn, auth)
        entry = GrantSweepstakesEntryUseCase(auth).execute(
            conn, campaign_id=campaign_id, customer_id=new_uuid(),
            entry_method=SweepstakesEntryMethod.MANUAL_GRANT, actor_user_id=new_uuid(),
            operation_id=new_uuid(), chances_granted=1)
        ticket = IssueSweepstakesTicketUseCase(auth).execute(
            conn, campaign_id=campaign_id, entry_id=entry.entity_id, actor_user_id=new_uuid(),
            operation_id=new_uuid())
        first = PrintSweepstakesTicketUseCase(auth).execute(
            conn, ticket_id=ticket.entity_id, actor_user_id=new_uuid(),
            actor_branch_id=new_uuid(), operation_id=new_uuid())
        assert first.success
        assert first.data["print_count"] == 1
        second = PrintSweepstakesTicketUseCase(auth).execute(
            conn, ticket_id=ticket.entity_id, actor_user_id=new_uuid(),
            actor_branch_id=new_uuid(), operation_id=new_uuid())
        assert second.success
        assert second.data["print_count"] == 2

    def test_void_ticket(self, conn, auth):
        campaign_id = _active_campaign(conn, auth)
        entry = GrantSweepstakesEntryUseCase(auth).execute(
            conn, campaign_id=campaign_id, customer_id=new_uuid(),
            entry_method=SweepstakesEntryMethod.MANUAL_GRANT, actor_user_id=new_uuid(),
            operation_id=new_uuid(), chances_granted=1)
        ticket = IssueSweepstakesTicketUseCase(auth).execute(
            conn, campaign_id=campaign_id, entry_id=entry.entity_id, actor_user_id=new_uuid(),
            operation_id=new_uuid())
        result = VoidSweepstakesTicketUseCase(auth).execute(
            conn, ticket_id=ticket.entity_id, reason="venta cancelada", actor_user_id=new_uuid(),
            actor_branch_id=new_uuid(), operation_id=new_uuid())
        assert result.success


class TestDrawAndWinnerFlow:
    def _campaign_with_tickets(self, conn, auth, *, ticket_count: int):
        campaign_id = _active_campaign(conn, auth)
        AddSweepstakesPrizeUseCase(auth).execute(
            conn, campaign_id=campaign_id, name="Televisión", actor_user_id=new_uuid(),
            operation_id=new_uuid(), quantity=1, rank=1)
        ticket_ids = []
        for _ in range(ticket_count):
            entry = GrantSweepstakesEntryUseCase(auth).execute(
                conn, campaign_id=campaign_id, customer_id=new_uuid(),
                entry_method=SweepstakesEntryMethod.MANUAL_GRANT, actor_user_id=new_uuid(),
                operation_id=new_uuid(), chances_granted=1)
            ticket = IssueSweepstakesTicketUseCase(auth).execute(
                conn, campaign_id=campaign_id, entry_id=entry.entity_id,
                actor_user_id=new_uuid(), operation_id=new_uuid())
            ticket_ids.append(ticket.entity_id)
        return campaign_id, ticket_ids

    def test_execute_draw_selects_one_winner(self, conn, auth):
        campaign_id, ticket_ids = self._campaign_with_tickets(conn, auth, ticket_count=5)
        draw = ScheduleSweepstakesDrawUseCase(auth).execute(
            conn, campaign_id=campaign_id, actor_user_id=new_uuid(), operation_id=new_uuid())
        assert draw.success
        result = ExecuteSweepstakesDrawUseCase(auth).execute(
            conn, draw_id=draw.entity_id, actor_user_id=new_uuid(), operation_id=new_uuid())
        assert result.success
        assert len(result.data["winners"]) == 1
        assert result.data["pool_size"] == 5
        assert result.data["winners"][0] is not None

    def test_execute_draw_fails_on_empty_pool(self, conn, auth):
        campaign_id = _active_campaign(conn, auth)
        draw = ScheduleSweepstakesDrawUseCase(auth).execute(
            conn, campaign_id=campaign_id, actor_user_id=new_uuid(), operation_id=new_uuid())
        result = ExecuteSweepstakesDrawUseCase(auth).execute(
            conn, draw_id=draw.entity_id, actor_user_id=new_uuid(), operation_id=new_uuid())
        assert not result.success
        assert result.error_code == "EMPTY_TICKET_POOL"

    def test_cancel_scheduled_draw(self, conn, auth):
        campaign_id, _ = self._campaign_with_tickets(conn, auth, ticket_count=1)
        draw = ScheduleSweepstakesDrawUseCase(auth).execute(
            conn, campaign_id=campaign_id, actor_user_id=new_uuid(), operation_id=new_uuid())
        result = CancelSweepstakesDrawUseCase(auth).execute(
            conn, draw_id=draw.entity_id, actor_user_id=new_uuid(), operation_id=new_uuid())
        assert result.success

    def test_validate_and_deliver_winner(self, conn, auth):
        from backend.infrastructure.db.repositories.sweepstakes.unit_of_work import (
            SweepstakesUnitOfWork,
        )

        campaign_id, _ = self._campaign_with_tickets(conn, auth, ticket_count=3)
        draw = ScheduleSweepstakesDrawUseCase(auth).execute(
            conn, campaign_id=campaign_id, actor_user_id=new_uuid(), operation_id=new_uuid())
        executed = ExecuteSweepstakesDrawUseCase(auth).execute(
            conn, draw_id=draw.entity_id, actor_user_id=new_uuid(), operation_id=new_uuid())
        winner_id = executed.data["winners"][0]

        validate = ValidateSweepstakesWinnerUseCase(auth).execute(
            conn, winner_id=winner_id, actor_user_id=new_uuid(), operation_id=new_uuid())
        assert validate.success
        deliver = DeliverSweepstakesPrizeUseCase(auth).execute(
            conn, winner_id=winner_id, actor_user_id=new_uuid(), operation_id=new_uuid())
        assert deliver.success

        with SweepstakesUnitOfWork(conn) as uow:
            winner = uow.winners.get(winner_id)
            assert winner.status.value == "PRIZE_DELIVERED"

    def test_disqualify_winner(self, conn, auth):
        campaign_id, _ = self._campaign_with_tickets(conn, auth, ticket_count=2)
        draw = ScheduleSweepstakesDrawUseCase(auth).execute(
            conn, campaign_id=campaign_id, actor_user_id=new_uuid(), operation_id=new_uuid())
        executed = ExecuteSweepstakesDrawUseCase(auth).execute(
            conn, draw_id=draw.entity_id, actor_user_id=new_uuid(), operation_id=new_uuid())
        winner_id = executed.data["winners"][0]
        result = DisqualifySweepstakesWinnerUseCase(auth).execute(
            conn, winner_id=winner_id, reason="datos falsos", actor_user_id=new_uuid(),
            operation_id=new_uuid())
        assert result.success

    def test_second_draw_excludes_prior_winner(self, conn, auth):
        campaign_id, ticket_ids = self._campaign_with_tickets(conn, auth, ticket_count=3)
        draw1 = ScheduleSweepstakesDrawUseCase(auth).execute(
            conn, campaign_id=campaign_id, actor_user_id=new_uuid(), operation_id=new_uuid())
        result1 = ExecuteSweepstakesDrawUseCase(auth).execute(
            conn, draw_id=draw1.entity_id, actor_user_id=new_uuid(), operation_id=new_uuid())
        assert result1.data["pool_size"] == 3

        AddSweepstakesPrizeUseCase(auth).execute(
            conn, campaign_id=campaign_id, name="Segundo premio", actor_user_id=new_uuid(),
            operation_id=new_uuid(), quantity=1, rank=2)
        draw2 = ScheduleSweepstakesDrawUseCase(auth).execute(
            conn, campaign_id=campaign_id, actor_user_id=new_uuid(), operation_id=new_uuid())
        result2 = ExecuteSweepstakesDrawUseCase(auth).execute(
            conn, draw_id=draw2.entity_id, actor_user_id=new_uuid(), operation_id=new_uuid())
        assert result2.success
        assert result2.data["pool_size"] == 2
