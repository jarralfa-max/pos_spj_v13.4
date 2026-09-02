"""LOY-23 — Loyalty digital card projection use cases (master prompt §48)."""

from __future__ import annotations

import sqlite3

import pytest

from backend.application.loyalty_cards.authorization import LoyaltyCardsAuthorizationPolicy
from backend.application.loyalty_cards.use_cases.card_use_cases import IssueLoyaltyCardUseCase
from backend.application.loyalty_cards.use_cases.digital_card_use_cases import (
    CreateLoyaltyDigitalCardProjectionUseCase,
    GetLoyaltyDigitalCardProjectionUseCase,
    RefreshLoyaltyDigitalCardProjectionUseCase,
)
from backend.domain.loyalty_cards.enums import LoyaltyCardType
from backend.infrastructure.db.schema.loyalty_cards_schema import create_loyalty_cards_schema
from backend.shared.ids import new_uuid


@pytest.fixture
def conn():
    c = sqlite3.connect(":memory:")
    c.execute("PRAGMA foreign_keys = ON")
    create_loyalty_cards_schema(c)
    c.commit()
    yield c
    c.close()


@pytest.fixture
def auth():
    return LoyaltyCardsAuthorizationPolicy.permissive_for_tests()


def _digital_card(conn, auth):
    result = IssueLoyaltyCardUseCase(auth).execute(
        conn, customer_id=new_uuid(), membership_id=new_uuid(), card_type=LoyaltyCardType.DIGITAL,
        actor_user_id=new_uuid(), actor_branch_id=new_uuid(), operation_id=new_uuid())
    return result.entity_id


def _physical_card(conn, auth):
    result = IssueLoyaltyCardUseCase(auth).execute(
        conn, customer_id=new_uuid(), membership_id=new_uuid(), card_type=LoyaltyCardType.PHYSICAL,
        actor_user_id=new_uuid(), actor_branch_id=new_uuid(), operation_id=new_uuid())
    return result.entity_id


class TestCreateProjection:
    def test_create_for_digital_card(self, conn, auth):
        card_id = _digital_card(conn, auth)
        result = CreateLoyaltyDigitalCardProjectionUseCase(auth).execute(
            conn, card_id=card_id, display_fields={"customer_name": "Ana"},
            actor_user_id=new_uuid(), operation_id=new_uuid())
        assert result.success

    def test_rejects_physical_card(self, conn, auth):
        card_id = _physical_card(conn, auth)
        result = CreateLoyaltyDigitalCardProjectionUseCase(auth).execute(
            conn, card_id=card_id, display_fields={}, actor_user_id=new_uuid(),
            operation_id=new_uuid())
        assert not result.success
        assert result.error_code == "INVALID_DIGITAL_PROJECTION"

    def test_rejects_duplicate(self, conn, auth):
        card_id = _digital_card(conn, auth)
        CreateLoyaltyDigitalCardProjectionUseCase(auth).execute(
            conn, card_id=card_id, display_fields={}, actor_user_id=new_uuid(),
            operation_id=new_uuid())
        result = CreateLoyaltyDigitalCardProjectionUseCase(auth).execute(
            conn, card_id=card_id, display_fields={}, actor_user_id=new_uuid(),
            operation_id=new_uuid())
        assert not result.success
        assert result.error_code == "DIGITAL_PROJECTION_ALREADY_EXISTS"

    def test_card_not_found(self, conn, auth):
        result = CreateLoyaltyDigitalCardProjectionUseCase(auth).execute(
            conn, card_id=new_uuid(), display_fields={}, actor_user_id=new_uuid(),
            operation_id=new_uuid())
        assert not result.success
        assert result.error_code == "CARD_NOT_FOUND"


class TestRefreshAndGet:
    def test_refresh_and_get(self, conn, auth):
        card_id = _digital_card(conn, auth)
        CreateLoyaltyDigitalCardProjectionUseCase(auth).execute(
            conn, card_id=card_id, display_fields={"points_balance": "0"},
            actor_user_id=new_uuid(), operation_id=new_uuid())
        refresh = RefreshLoyaltyDigitalCardProjectionUseCase(auth).execute(
            conn, card_id=card_id, display_fields={"points_balance": "150"},
            actor_user_id=new_uuid(), operation_id=new_uuid())
        assert refresh.success

        result = GetLoyaltyDigitalCardProjectionUseCase(auth).execute(
            conn, card_id=card_id, actor_user_id=new_uuid(), operation_id=new_uuid())
        assert result.success
        assert result.data["display_fields"] == {"points_balance": "150"}

    def test_refresh_not_found(self, conn, auth):
        result = RefreshLoyaltyDigitalCardProjectionUseCase(auth).execute(
            conn, card_id=new_uuid(), display_fields={}, actor_user_id=new_uuid(),
            operation_id=new_uuid())
        assert not result.success
        assert result.error_code == "DIGITAL_PROJECTION_NOT_FOUND"

    def test_get_not_found(self, conn, auth):
        result = GetLoyaltyDigitalCardProjectionUseCase(auth).execute(
            conn, card_id=new_uuid(), actor_user_id=new_uuid(), operation_id=new_uuid())
        assert not result.success
        assert result.error_code == "DIGITAL_PROJECTION_NOT_FOUND"
