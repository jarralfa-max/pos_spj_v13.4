"""LOY-15 — Sweepstakes domain entities (master prompt §27-28)."""

from __future__ import annotations

from decimal import Decimal

import pytest

from backend.domain.sweepstakes.entities.sweepstakes_campaign import SweepstakesCampaign
from backend.domain.sweepstakes.entities.sweepstakes_draw import SweepstakesDraw
from backend.domain.sweepstakes.entities.sweepstakes_entry import SweepstakesEntry
from backend.domain.sweepstakes.entities.sweepstakes_prize import SweepstakesPrize
from backend.domain.sweepstakes.entities.sweepstakes_rule import SweepstakesRule
from backend.domain.sweepstakes.entities.sweepstakes_ticket import SweepstakesTicket
from backend.domain.sweepstakes.entities.sweepstakes_winner import SweepstakesWinner
from backend.domain.sweepstakes.enums import SweepstakesEntryMethod
from backend.domain.sweepstakes.exceptions import (
    EmptyTicketPoolError,
    InvalidSweepstakesCampaignError,
    InvalidSweepstakesCampaignStateError,
    InvalidSweepstakesRuleError,
    InvalidSweepstakesTicketStateError,
    InvalidSweepstakesWinnerStateError,
    TicketRequiresExistingEntryError,
)
from backend.domain.sweepstakes.policies.draw_policy import SweepstakesDrawPolicy
from backend.shared.ids import new_uuid


class TestSweepstakesCampaign:
    def test_create_requires_code_and_name(self):
        with pytest.raises(InvalidSweepstakesCampaignError):
            SweepstakesCampaign.create("", "Rifa", created_by_user_id=new_uuid())

    def test_ticket_price_must_be_decimal(self):
        with pytest.raises(InvalidSweepstakesCampaignError):
            SweepstakesCampaign.create("R1", "Rifa", created_by_user_id=new_uuid(),
                                        ticket_price=1.5)

    def test_lifecycle_happy_path(self):
        creator = new_uuid()
        campaign = SweepstakesCampaign.create("R1", "Rifa", created_by_user_id=creator)
        campaign.submit_for_approval()
        campaign.approve(new_uuid())
        campaign.activate()
        assert campaign.is_active()
        assert campaign.accepts_entries()
        campaign.mark_drawn()
        campaign.close()
        assert campaign.status.value == "CLOSED"

    def test_approver_cannot_be_creator(self):
        creator = new_uuid()
        campaign = SweepstakesCampaign.create("R1", "Rifa", created_by_user_id=creator)
        campaign.submit_for_approval()
        with pytest.raises(InvalidSweepstakesCampaignStateError):
            campaign.approve(creator)

    def test_cannot_activate_from_draft(self):
        campaign = SweepstakesCampaign.create("R1", "Rifa", created_by_user_id=new_uuid())
        with pytest.raises(InvalidSweepstakesCampaignStateError):
            campaign.activate()

    def test_pause_resume(self):
        campaign = SweepstakesCampaign.create("R1", "Rifa", created_by_user_id=new_uuid())
        campaign.submit_for_approval()
        campaign.approve(new_uuid())
        campaign.activate()
        campaign.pause()
        assert not campaign.accepts_entries()
        campaign.resume()
        assert campaign.accepts_entries()


class TestSweepstakesRule:
    def test_purchase_amount_requires_positive_amount(self):
        with pytest.raises(InvalidSweepstakesRuleError):
            SweepstakesRule.create(new_uuid(), SweepstakesEntryMethod.PURCHASE_AMOUNT,
                                    amount_per_ticket=Decimal("0"))

    def test_chances_for_amount(self):
        rule = SweepstakesRule.create(new_uuid(), SweepstakesEntryMethod.PURCHASE_AMOUNT,
                                       amount_per_ticket=Decimal("100"))
        assert rule.chances_for_amount(Decimal("350")) == 3
        assert rule.chances_for_amount(Decimal("50")) == 0

    def test_chances_capped_by_max_per_sale(self):
        rule = SweepstakesRule.create(new_uuid(), SweepstakesEntryMethod.PURCHASE_AMOUNT,
                                       amount_per_ticket=Decimal("10"), max_tickets_per_sale=5)
        assert rule.chances_for_amount(Decimal("1000")) == 5

    def test_flat_grant_for_non_purchase_method(self):
        rule = SweepstakesRule.create(new_uuid(), SweepstakesEntryMethod.MANUAL_GRANT,
                                       tickets_per_sale=2)
        assert rule.chances_for_amount(Decimal("0")) == 2


class TestSweepstakesPrize:
    def test_requires_positive_quantity(self):
        with pytest.raises(Exception):
            SweepstakesPrize.create(new_uuid(), "TV", quantity=0)

    def test_mark_delivered(self):
        prize = SweepstakesPrize.create(new_uuid(), "TV")
        prize.mark_assigned()
        prize.mark_delivered()
        assert prize.status.value == "DELIVERED"


class TestSweepstakesEntry:
    def test_purchase_amount_requires_source_sale(self):
        with pytest.raises(Exception):
            SweepstakesEntry.grant(new_uuid(), new_uuid(), SweepstakesEntryMethod.PURCHASE_AMOUNT)

    def test_manual_grant_ok(self):
        entry = SweepstakesEntry.grant(new_uuid(), new_uuid(), SweepstakesEntryMethod.MANUAL_GRANT,
                                        chances_granted=3)
        assert entry.chances_granted == 3


class TestSweepstakesTicket:
    def test_cannot_create_without_entry_id(self):
        with pytest.raises(TicketRequiresExistingEntryError):
            SweepstakesTicket(id=new_uuid(), campaign_id=new_uuid(), entry_id="",
                               customer_id=new_uuid(), ticket_number="R1-000001")

    def test_issue_starts_as_issued(self):
        ticket = SweepstakesTicket.issue(new_uuid(), new_uuid(), new_uuid(), "R1-000001")
        assert ticket.status.value == "ISSUED"
        assert ticket.print_count == 0

    def test_print_then_reprint_same_ticket(self):
        ticket = SweepstakesTicket.issue(new_uuid(), new_uuid(), new_uuid(), "R1-000001")
        ticket.record_print()
        assert ticket.status.value == "PRINTED"
        assert ticket.print_count == 1
        first_printed = ticket.first_printed_at
        ticket.record_print()
        assert ticket.print_count == 2
        assert ticket.first_printed_at == first_printed

    def test_cannot_print_void_ticket(self):
        ticket = SweepstakesTicket.issue(new_uuid(), new_uuid(), new_uuid(), "R1-000001")
        ticket.void("venta cancelada")
        with pytest.raises(InvalidSweepstakesTicketStateError):
            ticket.record_print()

    def test_void_requires_reason(self):
        ticket = SweepstakesTicket.issue(new_uuid(), new_uuid(), new_uuid(), "R1-000001")
        with pytest.raises(InvalidSweepstakesTicketStateError):
            ticket.void("")

    def test_is_eligible(self):
        ticket = SweepstakesTicket.issue(new_uuid(), new_uuid(), new_uuid(), "R1-000001")
        assert ticket.is_eligible()
        ticket.void("motivo")
        assert not ticket.is_eligible()


class TestSweepstakesDraw:
    def test_complete_requires_nonempty_pool(self):
        draw = SweepstakesDraw.schedule(new_uuid())
        with pytest.raises(EmptyTicketPoolError):
            draw.complete(executed_by_user_id=new_uuid(), random_seed="abc",
                          pool_hash="hash", ticket_pool_size=0)

    def test_complete_happy_path(self):
        draw = SweepstakesDraw.schedule(new_uuid())
        draw.complete(executed_by_user_id=new_uuid(), random_seed="abc", pool_hash="hash",
                      ticket_pool_size=10)
        assert draw.status.value == "COMPLETED"

    def test_cancel_only_from_scheduled(self):
        draw = SweepstakesDraw.schedule(new_uuid())
        draw.complete(executed_by_user_id=new_uuid(), random_seed="abc", pool_hash="hash",
                      ticket_pool_size=10)
        with pytest.raises(Exception):
            draw.cancel()


class TestSweepstakesWinner:
    def test_validate_then_deliver(self):
        winner = SweepstakesWinner.select(new_uuid(), new_uuid(), new_uuid(), new_uuid(),
                                           new_uuid())
        winner.validate(new_uuid())
        winner.deliver_prize(new_uuid())
        assert winner.status.value == "PRIZE_DELIVERED"

    def test_cannot_deliver_without_validation(self):
        winner = SweepstakesWinner.select(new_uuid(), new_uuid(), new_uuid(), new_uuid(),
                                           new_uuid())
        with pytest.raises(InvalidSweepstakesWinnerStateError):
            winner.deliver_prize(new_uuid())

    def test_disqualify_requires_reason(self):
        winner = SweepstakesWinner.select(new_uuid(), new_uuid(), new_uuid(), new_uuid(),
                                           new_uuid())
        with pytest.raises(InvalidSweepstakesWinnerStateError):
            winner.disqualify("")

    def test_cannot_disqualify_after_delivered(self):
        winner = SweepstakesWinner.select(new_uuid(), new_uuid(), new_uuid(), new_uuid(),
                                           new_uuid())
        winner.validate(new_uuid())
        winner.deliver_prize(new_uuid())
        with pytest.raises(InvalidSweepstakesWinnerStateError):
            winner.disqualify("motivo")


class TestSweepstakesDrawPolicy:
    def test_eligible_tickets_excludes_void_and_prior_winners(self):
        t1 = SweepstakesTicket.issue(new_uuid(), new_uuid(), new_uuid(), "R1-000001")
        t2 = SweepstakesTicket.issue(new_uuid(), new_uuid(), new_uuid(), "R1-000002")
        t3 = SweepstakesTicket.issue(new_uuid(), new_uuid(), new_uuid(), "R1-000003")
        t3.void("motivo")
        eligible = SweepstakesDrawPolicy.eligible_tickets(
            [t1, t2, t3], exclude_ticket_ids=frozenset({t2.id}))
        assert eligible == [t1]

    def test_pool_hash_is_order_independent(self):
        t1 = SweepstakesTicket.issue(new_uuid(), new_uuid(), new_uuid(), "R1-000001")
        t2 = SweepstakesTicket.issue(new_uuid(), new_uuid(), new_uuid(), "R1-000002")
        assert (SweepstakesDrawPolicy.pool_hash([t1, t2])
                == SweepstakesDrawPolicy.pool_hash([t2, t1]))
