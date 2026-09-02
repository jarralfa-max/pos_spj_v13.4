"""LOY-24 — GrantSweepstakesEntryFromSaleUseCase (master prompt §54): the
Sales integration hook LOY-15 originally flagged as missing."""

from __future__ import annotations

import sqlite3
from decimal import Decimal

import pytest

from backend.application.loyalty.authorization import LoyaltyAuthorizationPolicy
from backend.application.sweepstakes.use_cases.campaign_use_cases import (
    ActivateSweepstakesCampaignUseCase,
    ApproveSweepstakesCampaignUseCase,
    ConfigureSweepstakesRuleUseCase,
    CreateSweepstakesCampaignUseCase,
)
from backend.application.sweepstakes.use_cases.entry_use_cases import (
    GrantSweepstakesEntryFromSaleUseCase,
)
from backend.domain.sweepstakes.enums import SweepstakesEntryMethod
from backend.infrastructure.db.repositories.sweepstakes.unit_of_work import SweepstakesUnitOfWork
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


def _active_campaign_with_rule(conn, auth, *, amount_per_ticket=Decimal("100"),
                                max_tickets_per_customer=0):
    create = CreateSweepstakesCampaignUseCase(auth).execute(
        conn, code="PROMO1", name="Promo de verano", actor_user_id=new_uuid(),
        operation_id=new_uuid(), max_tickets_per_customer=max_tickets_per_customer)
    ApproveSweepstakesCampaignUseCase(auth).execute(
        conn, campaign_id=create.entity_id, actor_user_id=new_uuid(), operation_id=new_uuid())
    ActivateSweepstakesCampaignUseCase(auth).execute(
        conn, campaign_id=create.entity_id, actor_user_id=new_uuid(), operation_id=new_uuid())
    ConfigureSweepstakesRuleUseCase(auth).execute(
        conn, campaign_id=create.entity_id, entry_method=SweepstakesEntryMethod.PURCHASE_AMOUNT,
        actor_user_id=new_uuid(), operation_id=new_uuid(), amount_per_ticket=amount_per_ticket)
    return create.entity_id


class TestGrantSweepstakesEntryFromSale:
    def test_grants_entry_for_qualifying_sale(self, conn, auth):
        campaign_id = _active_campaign_with_rule(conn, auth)
        customer_id = new_uuid()
        result = GrantSweepstakesEntryFromSaleUseCase().execute(
            conn, campaign_id=campaign_id, customer_id=customer_id, source_sale_id=new_uuid(),
            sale_amount=Decimal("350"), actor_branch_id=new_uuid(), operation_id=new_uuid())
        assert result.success
        assert result.data["granted"] is True
        assert result.data["chances_granted"] == 3
        with SweepstakesUnitOfWork(conn) as uow:
            entry = uow.entries.get(result.entity_id)
            assert entry.chances_granted == 3
            assert entry.entry_method.value == "PURCHASE_AMOUNT"

    def test_no_grant_when_amount_too_low(self, conn, auth):
        campaign_id = _active_campaign_with_rule(conn, auth)
        result = GrantSweepstakesEntryFromSaleUseCase().execute(
            conn, campaign_id=campaign_id, customer_id=new_uuid(), source_sale_id=new_uuid(),
            sale_amount=Decimal("50"), actor_branch_id=new_uuid(), operation_id=new_uuid())
        assert result.success
        assert result.data["granted"] is False

    def test_no_grant_when_campaign_not_active(self, conn, auth):
        create = CreateSweepstakesCampaignUseCase(auth).execute(
            conn, code="PROMO2", name="Promo inactiva", actor_user_id=new_uuid(),
            operation_id=new_uuid())
        result = GrantSweepstakesEntryFromSaleUseCase().execute(
            conn, campaign_id=create.entity_id, customer_id=new_uuid(), source_sale_id=new_uuid(),
            sale_amount=Decimal("500"), actor_branch_id=new_uuid(), operation_id=new_uuid())
        assert result.success
        assert result.data["granted"] is False

    def test_no_grant_when_no_purchase_amount_rule(self, conn, auth):
        create = CreateSweepstakesCampaignUseCase(auth).execute(
            conn, code="PROMO3", name="Sin regla", actor_user_id=new_uuid(),
            operation_id=new_uuid())
        ApproveSweepstakesCampaignUseCase(auth).execute(
            conn, campaign_id=create.entity_id, actor_user_id=new_uuid(), operation_id=new_uuid())
        ActivateSweepstakesCampaignUseCase(auth).execute(
            conn, campaign_id=create.entity_id, actor_user_id=new_uuid(), operation_id=new_uuid())
        result = GrantSweepstakesEntryFromSaleUseCase().execute(
            conn, campaign_id=create.entity_id, customer_id=new_uuid(), source_sale_id=new_uuid(),
            sale_amount=Decimal("500"), actor_branch_id=new_uuid(), operation_id=new_uuid())
        assert result.success
        assert result.data["granted"] is False

    def test_campaign_not_found(self, conn, auth):
        result = GrantSweepstakesEntryFromSaleUseCase().execute(
            conn, campaign_id=new_uuid(), customer_id=new_uuid(), source_sale_id=new_uuid(),
            sale_amount=Decimal("500"), actor_branch_id=new_uuid(), operation_id=new_uuid())
        assert not result.success
        assert result.error_code == "CAMPAIGN_NOT_FOUND"

    def test_caps_at_max_tickets_per_customer(self, conn, auth):
        campaign_id = _active_campaign_with_rule(
            conn, auth, amount_per_ticket=Decimal("100"), max_tickets_per_customer=2)
        customer_id = new_uuid()
        first = GrantSweepstakesEntryFromSaleUseCase().execute(
            conn, campaign_id=campaign_id, customer_id=customer_id, source_sale_id=new_uuid(),
            sale_amount=Decimal("150"), actor_branch_id=new_uuid(), operation_id=new_uuid())
        assert first.data["chances_granted"] == 1

        second = GrantSweepstakesEntryFromSaleUseCase().execute(
            conn, campaign_id=campaign_id, customer_id=customer_id, source_sale_id=new_uuid(),
            sale_amount=Decimal("500"), actor_branch_id=new_uuid(), operation_id=new_uuid())
        assert second.data["granted"] is True
        assert second.data["chances_granted"] == 1  # capped: 2 max - 1 already granted

    def test_no_authenticated_actor_required(self, conn, auth):
        """System-triggered — never gates on a live user session."""
        campaign_id = _active_campaign_with_rule(conn, auth)
        result = GrantSweepstakesEntryFromSaleUseCase().execute(
            conn, campaign_id=campaign_id, customer_id=new_uuid(), source_sale_id=new_uuid(),
            sale_amount=Decimal("200"), actor_branch_id=new_uuid(), operation_id=new_uuid())
        assert result.success
