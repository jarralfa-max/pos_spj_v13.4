"""LOY-20 — sheet/imposition profile use cases (master prompt §38-40)."""

from __future__ import annotations

import sqlite3
from decimal import Decimal

import pytest

from backend.application.loyalty_cards.authorization import LoyaltyCardsAuthorizationPolicy
from backend.application.loyalty_cards.use_cases.sheet_use_cases import (
    CreateImpositionProfileUseCase,
    CreateSheetProfileUseCase,
    CreateStandard12x18SheetProfileUseCase,
)
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


class TestCreateSheetProfile:
    def test_create(self, conn, auth):
        result = CreateSheetProfileUseCase(auth).execute(
            conn, code="S1", name="Pliego personalizado", width_mm=Decimal("300"),
            height_mm=Decimal("450"), actor_user_id=new_uuid(), actor_branch_id=new_uuid(),
            operation_id=new_uuid())
        assert result.success
        assert Decimal(result.data["printable_width_mm"]) == Decimal("300")

    def test_standard_12x18(self, conn, auth):
        result = CreateStandard12x18SheetProfileUseCase(auth).execute(
            conn, actor_user_id=new_uuid(), actor_branch_id=new_uuid(), operation_id=new_uuid())
        assert result.success


class TestCreateImpositionProfile:
    def test_create_imposition(self, conn, auth):
        sheet = CreateStandard12x18SheetProfileUseCase(auth).execute(
            conn, actor_user_id=new_uuid(), actor_branch_id=new_uuid(), operation_id=new_uuid())
        result = CreateImpositionProfileUseCase(auth).execute(
            conn, sheet_profile_id=sheet.entity_id, card_width_mm=Decimal("85.6"),
            card_height_mm=Decimal("54"), actor_user_id=new_uuid(), actor_branch_id=new_uuid(),
            operation_id=new_uuid())
        assert result.success
        assert result.data["cards_per_sheet"] > 0

    def test_sheet_not_found(self, conn, auth):
        result = CreateImpositionProfileUseCase(auth).execute(
            conn, sheet_profile_id=new_uuid(), card_width_mm=Decimal("85.6"),
            card_height_mm=Decimal("54"), actor_user_id=new_uuid(), actor_branch_id=new_uuid(),
            operation_id=new_uuid())
        assert not result.success
        assert result.error_code == "SHEET_PROFILE_NOT_FOUND"

    def test_card_too_big_for_sheet(self, conn, auth):
        sheet = CreateSheetProfileUseCase(auth).execute(
            conn, code="TINY", name="Pliego pequeño", width_mm=Decimal("50"),
            height_mm=Decimal("50"), actor_user_id=new_uuid(), actor_branch_id=new_uuid(),
            operation_id=new_uuid())
        result = CreateImpositionProfileUseCase(auth).execute(
            conn, sheet_profile_id=sheet.entity_id, card_width_mm=Decimal("85.6"),
            card_height_mm=Decimal("54"), actor_user_id=new_uuid(), actor_branch_id=new_uuid(),
            operation_id=new_uuid())
        assert not result.success
        assert result.error_code == "CARD_DOES_NOT_FIT_ON_SHEET"
