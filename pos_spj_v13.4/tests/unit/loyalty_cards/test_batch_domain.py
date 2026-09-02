"""LOY-21 — LoyaltyCardBatch / LoyaltyCardBatchItem domain entities (master
prompt §43-44)."""

from __future__ import annotations

import pytest

from backend.domain.loyalty_cards.entities.loyalty_card_batch import LoyaltyCardBatch
from backend.domain.loyalty_cards.entities.loyalty_card_batch_item import LoyaltyCardBatchItem
from backend.domain.loyalty_cards.exceptions import (
    EmptyBatchError,
    InvalidLoyaltyCardBatchItemStateError,
    InvalidLoyaltyCardBatchStateError,
)
from backend.shared.ids import new_uuid


class TestLoyaltyCardBatch:
    def test_requires_at_least_one_item(self):
        with pytest.raises(EmptyBatchError):
            LoyaltyCardBatch.create(new_uuid(), new_uuid(), 0, 9, created_by_user_id=new_uuid())

    def test_sheets_required_ceiling_division(self):
        batch = LoyaltyCardBatch.create(new_uuid(), new_uuid(), 20, 9, created_by_user_id=new_uuid())
        assert batch.sheets_required == 3  # 20/9 -> 2.22 -> 3

    def test_exact_multiple(self):
        batch = LoyaltyCardBatch.create(new_uuid(), new_uuid(), 18, 9, created_by_user_id=new_uuid())
        assert batch.sheets_required == 2

    def test_lifecycle_happy_path(self):
        creator = new_uuid()
        batch = LoyaltyCardBatch.create(new_uuid(), new_uuid(), 5, 9, created_by_user_id=creator)
        batch.submit_for_approval()
        batch.approve(new_uuid())
        batch.start_printing()
        batch.complete()
        assert batch.status.value == "COMPLETED"

    def test_approver_cannot_be_creator(self):
        creator = new_uuid()
        batch = LoyaltyCardBatch.create(new_uuid(), new_uuid(), 5, 9, created_by_user_id=creator)
        batch.submit_for_approval()
        with pytest.raises(InvalidLoyaltyCardBatchStateError):
            batch.approve(creator)

    def test_cannot_print_before_approval(self):
        batch = LoyaltyCardBatch.create(new_uuid(), new_uuid(), 5, 9, created_by_user_id=new_uuid())
        with pytest.raises(InvalidLoyaltyCardBatchStateError):
            batch.start_printing()

    def test_cannot_cancel_completed(self):
        batch = LoyaltyCardBatch.create(new_uuid(), new_uuid(), 5, 9, created_by_user_id=new_uuid())
        batch.submit_for_approval()
        batch.approve(new_uuid())
        batch.start_printing()
        batch.complete()
        with pytest.raises(InvalidLoyaltyCardBatchStateError):
            batch.cancel()


class TestLoyaltyCardBatchItem:
    def test_sheet_and_position_derived_from_index(self):
        item0 = LoyaltyCardBatchItem.create_for_index(
            new_uuid(), new_uuid(), index=0, cards_per_sheet=9)
        item8 = LoyaltyCardBatchItem.create_for_index(
            new_uuid(), new_uuid(), index=8, cards_per_sheet=9)
        item9 = LoyaltyCardBatchItem.create_for_index(
            new_uuid(), new_uuid(), index=9, cards_per_sheet=9)
        assert (item0.sheet_number, item0.position_in_sheet) == (1, 1)
        assert (item8.sheet_number, item8.position_in_sheet) == (1, 9)
        assert (item9.sheet_number, item9.position_in_sheet) == (2, 1)

    def test_mark_printed(self):
        item = LoyaltyCardBatchItem.create_for_index(new_uuid(), new_uuid(), index=0,
                                                       cards_per_sheet=9)
        item.mark_printed()
        assert item.status.value == "PRINTED"
        assert item.printed_at is not None

    def test_cannot_mark_printed_twice(self):
        item = LoyaltyCardBatchItem.create_for_index(new_uuid(), new_uuid(), index=0,
                                                       cards_per_sheet=9)
        item.mark_printed()
        with pytest.raises(InvalidLoyaltyCardBatchItemStateError):
            item.mark_printed()

    def test_mark_failed_requires_reason(self):
        item = LoyaltyCardBatchItem.create_for_index(new_uuid(), new_uuid(), index=0,
                                                       cards_per_sheet=9)
        with pytest.raises(InvalidLoyaltyCardBatchItemStateError):
            item.mark_failed("")
