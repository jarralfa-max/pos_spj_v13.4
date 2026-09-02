"""LOY-2 — LoyaltyEvents catalog + payload contract (master prompt §62)."""

from __future__ import annotations

import pytest

from backend.domain.loyalty.events import (
    ALL_LOYALTY_EVENTS,
    FINANCE_ALIGNED_EVENTS,
    LoyaltyEvents,
    loyalty_event_payload,
)
from backend.shared.ids import new_uuid


class TestLoyaltyEventsCatalog:
    def test_covers_master_prompt_62_vocabulary(self):
        expected = {
            "LOYALTY_PROGRAM_CREATED", "LOYALTY_PROGRAM_ACTIVATED",
            "LOYALTY_MEMBERSHIP_ENROLLED", "LOYALTY_MEMBERSHIP_SUSPENDED",
            "LOYALTY_POINTS_ISSUED", "LOYALTY_POINTS_RESERVED",
            "LOYALTY_POINTS_REDEEMED", "LOYALTY_POINTS_RELEASED",
            "LOYALTY_POINTS_EXPIRED", "LOYALTY_POINTS_ADJUSTED",
            "LOYALTY_TRANSACTION_REVERSED", "LOYALTY_TIER_CHANGED",
            "LOYALTY_REWARD_GRANTED", "LOYALTY_CHALLENGE_COMPLETED",
            "LOYALTY_REFERRAL_QUALIFIED",
            # LOY-26 (§29): fraud case lifecycle, added after this test was
            # first written for LOY-2's own (smaller) §62 vocabulary.
            "LOYALTY_FRAUD_CASE_OPENED", "LOYALTY_FRAUD_CASE_CONFIRMED",
            "LOYALTY_FRAUD_CASE_DISMISSED",
        }
        assert expected == ALL_LOYALTY_EVENTS

    def test_finance_aligned_subset_matches_known_event_name_literals(self):
        """These 4 must stay byte-identical to
        backend.shared.events.event_names.EventName's own LOYALTY_* values —
        checked as literals here (not imported) to keep the domain layer
        free of an application-layer dependency."""
        assert FINANCE_ALIGNED_EVENTS == {
            "LOYALTY_POINTS_ISSUED", "LOYALTY_POINTS_EXPIRED",
            "LOYALTY_REWARD_GRANTED", "LOYALTY_TRANSACTION_REVERSED",
        }
        assert FINANCE_ALIGNED_EVENTS <= ALL_LOYALTY_EVENTS

    def test_legacy_bus_names_do_not_leak_into_the_new_catalog(self):
        assert "LOYALTY_POINTS_EARNED" not in ALL_LOYALTY_EVENTS
        assert "LOYALTY_CARD_ASSIGNED" not in ALL_LOYALTY_EVENTS


class TestLoyaltyEventPayload:
    def test_builds_valid_payload(self):
        operation_id, entity_id, branch_id, user_id = (new_uuid() for _ in range(4))
        payload = loyalty_event_payload(
            LoyaltyEvents.POINTS_ISSUED, operation_id=operation_id,
            entity_id=entity_id, branch_id=branch_id, user_id=user_id,
            points_amount="100")
        assert payload["event_name"] == LoyaltyEvents.POINTS_ISSUED
        assert payload["operation_id"] == operation_id
        assert payload["payload"]["points_amount"] == "100"

    def test_rejects_unknown_event_name(self):
        operation_id, entity_id, branch_id, user_id = (new_uuid() for _ in range(4))
        with pytest.raises(ValueError):
            loyalty_event_payload("NOT_A_REAL_EVENT", operation_id=operation_id,
                                   entity_id=entity_id, branch_id=branch_id, user_id=user_id)

    def test_rejects_non_uuidv7_ids(self):
        with pytest.raises(ValueError):
            loyalty_event_payload(LoyaltyEvents.POINTS_ISSUED, operation_id="not-a-uuid",
                                   entity_id=new_uuid(), branch_id=new_uuid(),
                                   user_id=new_uuid())
