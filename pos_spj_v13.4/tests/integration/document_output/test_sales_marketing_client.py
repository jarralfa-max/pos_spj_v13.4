"""SET-13 cutover — SalesMarketingClient against a real (in-memory)
SQLite born-clean schema. Context is built from only real data the client
actually supplies (`subtotal`/`total`/`has_customer`/`points_balance`) —
no fabricated business metric.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from backend.application.use_cases.configuracion.marketing_campaign_use_cases import CreateMarketingCampaignUseCase
from backend.domain.document_output.enums import RuleComparator
from backend.domain.document_output.entities.marketing_campaign import MarketingCampaign
from backend.domain.document_output.value_objects.campaign_rule import CampaignRule
from backend.infrastructure.db.repositories.document_output.marketing_campaign_repository import (
    SqliteMarketingCampaignRepository,
)
from backend.infrastructure.integrations.sales_marketing_client import SalesMarketingClient
from tests.integration._born_clean_db import make_db


@pytest.fixture
def conn():
    connection = make_db()
    yield connection
    connection.close()


class TestSelectTicketMessages:
    def test_returns_empty_tuple_when_no_campaigns_exist(self, conn):
        result = SalesMarketingClient(conn).select_ticket_messages(
            subtotal=Decimal("100"), total=Decimal("100"), has_customer=True, points_balance=10)
        assert result == ()

    def test_matching_campaign_renders(self, conn):
        CreateMarketingCampaignUseCase(conn).execute(
            code="low_pts", category="FOMO", message_template="Te quedan {points_balance} puntos.",
            rules=[CampaignRule.create(
                metric="points_balance", comparator=RuleComparator.LESS_THAN, threshold=Decimal("50"))],
        )
        result = SalesMarketingClient(conn).select_ticket_messages(
            subtotal=Decimal("100"), total=Decimal("100"), has_customer=True, points_balance=10)
        assert result == ("Te quedan 10 puntos.",)

    def test_non_matching_campaign_is_filtered(self, conn):
        CreateMarketingCampaignUseCase(conn).execute(
            code="high_pts", category="FOMO", message_template="Tienes muchos puntos.",
            rules=[CampaignRule.create(
                metric="points_balance", comparator=RuleComparator.GREATER_THAN, threshold=Decimal("1000"))],
        )
        result = SalesMarketingClient(conn).select_ticket_messages(
            subtotal=Decimal("100"), total=Decimal("100"), has_customer=True, points_balance=10)
        assert result == ()

    def test_inactive_campaign_is_excluded(self, conn):
        campaign = CreateMarketingCampaignUseCase(conn).execute(
            code="dormant", category="CTA", message_template="Nunca deberías ver esto.",
        )
        campaign.deactivate()
        SqliteMarketingCampaignRepository(conn).save(campaign)
        conn.commit()
        result = SalesMarketingClient(conn).select_ticket_messages(
            subtotal=Decimal("1"), total=Decimal("1"), has_customer=True, points_balance=0)
        assert result == ()

    def test_requires_customer_gates_a_campaign(self, conn):
        CreateMarketingCampaignUseCase(conn).execute(
            code="member_only", category="CTA", message_template="Bienvenido, socio.",
            requires_customer=True,
        )
        result_no_customer = SalesMarketingClient(conn).select_ticket_messages(
            subtotal=Decimal("1"), total=Decimal("1"), has_customer=False, points_balance=None)
        assert result_no_customer == ()

        result_with_customer = SalesMarketingClient(conn).select_ticket_messages(
            subtotal=Decimal("1"), total=Decimal("1"), has_customer=True, points_balance=None)
        assert result_with_customer == ("Bienvenido, socio.",)

    def test_cap_per_category_is_respected(self, conn):
        for i in range(4):
            CreateMarketingCampaignUseCase(conn).execute(
                code=f"fomo_{i}", category="FOMO", message_template=f"Mensaje {i}", priority=i,
                rules=[CampaignRule.create(
                    metric="total", comparator=RuleComparator.GREATER_THAN, threshold=Decimal("0"))],
            )
        result = SalesMarketingClient(conn).select_ticket_messages(
            subtotal=Decimal("10"), total=Decimal("10"), has_customer=True, points_balance=None)
        assert len(result) == 2  # FOMO capped at 2 in _MAX_PER_CATEGORY

    def test_highest_priority_wins_within_the_cap(self, conn):
        for i, priority in enumerate((5, 50, 20)):
            CreateMarketingCampaignUseCase(conn).execute(
                code=f"fomo_p{priority}", category="FOMO", message_template=f"P{priority}", priority=priority,
                rules=[CampaignRule.create(
                    metric="total", comparator=RuleComparator.GREATER_THAN, threshold=Decimal("0"))],
            )
        result = SalesMarketingClient(conn).select_ticket_messages(
            subtotal=Decimal("10"), total=Decimal("10"), has_customer=True, points_balance=None)
        assert result == ("P50", "P20")  # top 2 by priority, FOMO cap=2

    def test_malformed_template_referencing_missing_context_key_is_skipped_not_fatal(self, conn):
        CreateMarketingCampaignUseCase(conn).execute(
            code="bad_template", category="CTA", message_template="Hola {a_metric_we_never_supply}",
        )
        CreateMarketingCampaignUseCase(conn).execute(code="good_template", category="LOYALTY", message_template="Hola.")

        result = SalesMarketingClient(conn).select_ticket_messages(
            subtotal=Decimal("1"), total=Decimal("1"), has_customer=True, points_balance=None)
        assert result == ("Hola.",)
