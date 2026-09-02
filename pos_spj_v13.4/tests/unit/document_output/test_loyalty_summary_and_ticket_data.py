"""SET-13 — "Loyalty summary": LoyaltySummary + its integration into
TicketData (loyalty/messages fields). Pure domain — no DB.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from backend.domain.document_output.enums import DocumentType
from backend.domain.document_output.exceptions import DocumentInvalidValueError
from backend.domain.document_output.value_objects.loyalty_summary import LoyaltySummary
from backend.domain.document_output.value_objects.ticket_data import TicketData
from backend.domain.document_output.value_objects.ticket_line import TicketLine
from backend.domain.document_output.value_objects.ticket_party import TicketParty
from backend.domain.document_output.value_objects.ticket_totals import TicketTotals


class TestLoyaltySummaryCreate:
    def test_defaults_are_all_empty_and_unavailable(self):
        summary = LoyaltySummary.create()
        assert summary.points_earned is None
        assert summary.points_balance is None
        assert summary.tier == ""
        assert summary.available is False

    def test_valid_summary(self):
        summary = LoyaltySummary.create(points_earned=10, points_balance=250, tier="Oro", available=True)
        assert summary.points_balance == 250
        assert summary.tier == "Oro"

    @pytest.mark.parametrize("field_name", ["points_earned", "points_balance"])
    def test_rejects_negative_points(self, field_name):
        with pytest.raises(DocumentInvalidValueError):
            LoyaltySummary.create(**{field_name: -1})

    @pytest.mark.parametrize("field_name", ["points_earned", "points_balance"])
    def test_rejects_non_int(self, field_name):
        with pytest.raises(DocumentInvalidValueError):
            LoyaltySummary.create(**{field_name: 1.5})


def _line() -> TicketLine:
    return TicketLine.create(description="Carne", quantity=Decimal("1"), unit_price=Decimal("100"), line_total=Decimal("100"))


def _totals() -> TicketTotals:
    return TicketTotals.create(subtotal=Decimal("100"), discount=Decimal("0"), total=Decimal("100"))


class TestTicketDataWithLoyaltyAndMessages:
    def test_defaults_to_no_loyalty_and_no_messages(self):
        data = TicketData.create(
            document_type=DocumentType.SALE_TICKET, folio="VNT-1", issued_at="now",
            issuer=TicketParty.create(name="SPJ"), lines=[_line()], totals=_totals(),
        )
        assert data.loyalty is None
        assert data.messages == ()
        rendered = data.to_render_data()
        assert rendered["loyalty"] is None
        assert rendered["messages"] == []

    def test_loyalty_and_messages_flow_into_render_data(self):
        loyalty = LoyaltySummary.create(points_earned=10, points_balance=250, tier="Oro", available=True)
        data = TicketData.create(
            document_type=DocumentType.SALE_TICKET, folio="VNT-1", issued_at="now",
            issuer=TicketParty.create(name="SPJ"), lines=[_line()], totals=_totals(),
            loyalty=loyalty, messages=("Ganaste 10 puntos.", "Últimos 2 días de tu promoción."),
        )
        rendered = data.to_render_data()
        assert rendered["loyalty"] == {
            "points_earned": 10, "points_balance": 250, "tier": "Oro", "available": True,
        }
        assert rendered["messages"] == ["Ganaste 10 puntos.", "Últimos 2 días de tu promoción."]
