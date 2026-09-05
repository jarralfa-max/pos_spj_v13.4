# tests/test_quote_draft_entity.py — WA-11
from __future__ import annotations

import pytest

from domain.whatsapp.entities.quote_draft import (
    EmptyQuoteDraftError,
    QuoteDraft,
    QuoteDraftAlreadyFinalizedError,
    QuoteDraftNotYetCreatedError,
)
from domain.whatsapp.enums import QuoteDraftStatus


def _draft() -> QuoteDraft:
    return QuoteDraft.start(conversation_id="conv-1", branch_id="branch-1")


def _draft_with_line() -> QuoteDraft:
    draft = _draft()
    draft.add_line(product_external_id="p1", product_name="Bistec", quantity=2, unit="kg", unit_price=180.0)
    return draft


class TestStart:
    def test_starts_capturing(self):
        assert _draft().status == QuoteDraftStatus.CAPTURING

    def test_id_is_valid_uuidv7(self):
        from backend.shared.ids import is_uuidv7

        assert is_uuidv7(_draft().id)

    def test_requires_conversation_id(self):
        with pytest.raises(ValueError):
            QuoteDraft.start(conversation_id="")


class TestCapture:
    def test_add_line_updates_total(self):
        draft = _draft_with_line()
        assert draft.total == 360.0

    def test_cannot_add_line_after_created(self):
        draft = _draft_with_line()
        draft.mark_created(quote_external_id="q1", folio="COT-001")
        with pytest.raises(QuoteDraftAlreadyFinalizedError):
            draft.add_line(product_external_id="p2", product_name="Costilla", quantity=1, unit="kg", unit_price=90.0)

    def test_mark_created_requires_lines(self):
        with pytest.raises(EmptyQuoteDraftError):
            _draft().mark_created(quote_external_id="q1")

    def test_mark_created_sets_folio_and_external_id(self):
        draft = _draft_with_line()
        draft.mark_created(quote_external_id="q1", folio="COT-001")
        assert draft.status == QuoteDraftStatus.CREATED
        assert draft.quote_external_id == "q1"
        assert draft.folio == "COT-001"


class TestAcceptReject:
    def test_cannot_accept_before_created(self):
        draft = _draft_with_line()
        with pytest.raises(QuoteDraftNotYetCreatedError):
            draft.accept()

    def test_cannot_reject_before_created(self):
        draft = _draft_with_line()
        with pytest.raises(QuoteDraftNotYetCreatedError):
            draft.reject()

    def test_accept_after_created(self):
        draft = _draft_with_line()
        draft.mark_created(quote_external_id="q1", folio="COT-001")
        draft.accept()
        assert draft.status == QuoteDraftStatus.ACCEPTED
        assert draft.is_terminal() is True

    def test_reject_after_created(self):
        draft = _draft_with_line()
        draft.mark_created(quote_external_id="q1", folio="COT-001")
        draft.reject()
        assert draft.status == QuoteDraftStatus.REJECTED

    def test_cannot_accept_twice(self):
        draft = _draft_with_line()
        draft.mark_created(quote_external_id="q1")
        draft.accept()
        with pytest.raises(QuoteDraftAlreadyFinalizedError):
            draft.accept()

    def test_cannot_reject_an_accepted_quote(self):
        draft = _draft_with_line()
        draft.mark_created(quote_external_id="q1")
        draft.accept()
        with pytest.raises(QuoteDraftAlreadyFinalizedError):
            draft.reject()


class TestExpire:
    def test_expire_from_created(self):
        draft = _draft_with_line()
        draft.mark_created(quote_external_id="q1")
        draft.expire()
        assert draft.status == QuoteDraftStatus.EXPIRED

    def test_cannot_expire_twice(self):
        draft = _draft_with_line()
        draft.mark_created(quote_external_id="q1")
        draft.expire()
        with pytest.raises(QuoteDraftAlreadyFinalizedError):
            draft.expire()
