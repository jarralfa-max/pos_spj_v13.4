"""LOY-23 — LoyaltyDigitalCardProjection domain entity (master prompt §48)."""

from __future__ import annotations

import pytest

from backend.domain.loyalty_cards.entities.loyalty_digital_card_projection import (
    LoyaltyDigitalCardProjection,
)
from backend.domain.loyalty_cards.exceptions import InvalidDigitalCardProjectionError
from backend.shared.ids import new_uuid


class TestLoyaltyDigitalCardProjection:
    def test_requires_card_number_and_token(self):
        with pytest.raises(InvalidDigitalCardProjectionError):
            LoyaltyDigitalCardProjection.create(new_uuid(), new_uuid(), "", "tok")

    def test_create_with_display_fields(self):
        projection = LoyaltyDigitalCardProjection.create(
            new_uuid(), new_uuid(), "LC-001", "tok-abc",
            display_fields={"customer_name": "Ana"})
        assert projection.display_fields == {"customer_name": "Ana"}

    def test_refresh_replaces_entire_snapshot(self):
        projection = LoyaltyDigitalCardProjection.create(
            new_uuid(), new_uuid(), "LC-001", "tok-abc",
            display_fields={"customer_name": "Ana", "points_balance": "100"})
        projection.refresh({"customer_name": "Ana"})
        assert projection.display_fields == {"customer_name": "Ana"}
        assert "points_balance" not in projection.display_fields

    def test_refresh_can_rotate_token(self):
        projection = LoyaltyDigitalCardProjection.create(
            new_uuid(), new_uuid(), "LC-001", "tok-old")
        projection.refresh({}, qr_token="tok-new")
        assert projection.qr_token == "tok-new"

    def test_refresh_rejects_empty_token(self):
        projection = LoyaltyDigitalCardProjection.create(
            new_uuid(), new_uuid(), "LC-001", "tok-old")
        with pytest.raises(InvalidDigitalCardProjectionError):
            projection.refresh({}, qr_token="")

    def test_refresh_keeps_token_when_not_provided(self):
        projection = LoyaltyDigitalCardProjection.create(
            new_uuid(), new_uuid(), "LC-001", "tok-old")
        projection.refresh({"a": "b"})
        assert projection.qr_token == "tok-old"
