"""Quote / QuoteLine — reglas de dominio de Cotizaciones (CRM-43)."""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

import pytest

from backend.domain.quotes.entities import Quote
from backend.domain.quotes.enums import QuoteStatus
from backend.domain.quotes.exceptions import (
    InvalidQuoteStateError,
    QuoteSegregationError,
    QuoteValidationError,
)

TODAY = date(2026, 10, 9)
SOON = TODAY + timedelta(days=10)


def _quote(**kw) -> Quote:
    return Quote.create(quote_number="COT-000001", customer_id="c1", branch_id="b1",
                        valid_until=kw.pop("valid_until", SOON), created_by_user_id="seller",
                        today=TODAY, **kw)


def _line(quote, product="p1", qty="2", list_price="100", unit_price=None, min_price=None):
    return quote.add_line(product_id=product, product_code="X", description=product,
                          unit_code="KG", weighed=True, quantity_value=qty,
                          list_price=Decimal(list_price),
                          unit_price=None if unit_price is None else Decimal(unit_price),
                          min_price=None if min_price is None else Decimal(min_price))


class TestTotals:
    def test_list_price_by_default_and_totals(self):
        q = _quote()
        _line(q, qty="2.5", list_price="80")
        _line(q, product="p2", qty="5", list_price="115")
        assert q.total == Decimal("775.00") and q.discount_total == Decimal("0.00")
        assert not q.requires_approval

    def test_negotiated_price_requires_approval(self):
        q = _quote()
        line = _line(q, qty="12.5", list_price="80", unit_price="72", min_price="75")
        assert q.requires_approval and line.below_list and line.below_minimum
        assert q.list_subtotal == Decimal("1000.00") and q.total == Decimal("900.00")
        assert q.discount_total == Decimal("100.00")

    def test_same_product_twice_is_refused(self):
        q = _quote()
        _line(q)
        with pytest.raises(QuoteValidationError, match="ya está"):
            _line(q)

    def test_quantity_must_be_positive(self):
        with pytest.raises(QuoteValidationError):
            _line(_quote(), qty="0")

    def test_requantify_follows_list_unless_negotiated(self):
        q = _quote()
        at_list = _line(q, list_price="100")
        negotiated = _line(q, product="p2", list_price="100", unit_price="90")
        q.update_line(at_list.id, quantity_value="10", list_price=Decimal("95"))
        q.update_line(negotiated.id, quantity_value="10", list_price=Decimal("95"))
        assert at_list.unit_price == Decimal("95.00")
        assert negotiated.unit_price == Decimal("90.00")


class TestLifecycle:
    def test_submit_without_discount_is_approved(self):
        q = _quote()
        _line(q)
        q.submit(today=TODAY)
        assert q.status is QuoteStatus.APPROVED

    def test_submit_with_discount_waits_for_someone_else(self):
        q = _quote()
        _line(q, unit_price="90")
        q.submit(today=TODAY)
        assert q.status is QuoteStatus.PENDING_APPROVAL
        with pytest.raises(QuoteSegregationError):
            q.approve(approver_user_id="seller")
        q.approve(approver_user_id="manager", note="ok")
        assert q.status is QuoteStatus.APPROVED and q.approved_by_user_id == "manager"

    def test_empty_quote_cannot_be_submitted(self):
        with pytest.raises(QuoteValidationError, match="al menos un producto"):
            _quote().submit(today=TODAY)

    def test_only_drafts_are_edited(self):
        q = _quote()
        line = _line(q)
        q.submit(today=TODAY)
        with pytest.raises(InvalidQuoteStateError):
            q.update_line(line.id, unit_price="1")
        q.return_to_draft(reason="corregir")
        q.update_line(line.id, unit_price="99")
        assert q.status is QuoteStatus.DRAFT and q.approved_by_user_id is None

    def test_full_path_to_conversion(self):
        q = _quote()
        _line(q)
        q.submit(today=TODAY)
        q.send(today=TODAY)
        q.accept(today=TODAY)
        q.convert(order_id="o1")
        assert q.status is QuoteStatus.CONVERTED and q.converted_order_id == "o1"

    def test_cannot_convert_before_acceptance(self):
        q = _quote()
        _line(q)
        q.submit(today=TODAY)
        with pytest.raises(InvalidQuoteStateError):
            q.convert(order_id="o1")

    def test_expiry(self):
        q = _quote()
        _line(q)
        q.submit(today=TODAY)
        q.send(today=TODAY)
        later = SOON + timedelta(days=1)
        assert q.is_expired(later)
        with pytest.raises(InvalidQuoteStateError, match="venció"):
            q.accept(today=later)
        q.expire(today=later)
        assert q.status is QuoteStatus.EXPIRED

    def test_accepted_quote_does_not_expire(self):
        q = _quote()
        _line(q)
        q.submit(today=TODAY)
        q.accept(today=TODAY)
        assert not q.is_expired(SOON + timedelta(days=30))

    def test_reject_and_cancel_need_reasons(self):
        q = _quote()
        _line(q)
        q.submit(today=TODAY)
        with pytest.raises(QuoteValidationError):
            q.reject(reason=" ")
        with pytest.raises(QuoteValidationError):
            q.cancel(reason="")

    def test_past_validity_refused(self):
        with pytest.raises(QuoteValidationError, match="fecha pasada"):
            _quote(valid_until=TODAY - timedelta(days=1))

    def test_revision_replaces_a_live_quote(self):
        q = _quote()
        _line(q, unit_price="95")
        q.submit(today=TODAY)
        q.approve(approver_user_id="manager")
        q.send(today=TODAY)
        new = q.revise(quote_number="COT-000001/2", created_by_user_id="seller",
                       valid_until=SOON, today=TODAY)
        assert q.status is QuoteStatus.CANCELLED and "COT-000001/2" in q.cancel_reason
        assert new.status is QuoteStatus.DRAFT and new.revision == 2
        assert new.parent_quote_id == q.id and new.lines[0].unit_price == Decimal("95.00")
        assert new.lines[0].id != q.lines[0].id
