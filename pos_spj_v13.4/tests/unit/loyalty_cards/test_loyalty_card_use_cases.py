"""LOY-16 — Loyalty Card use cases (master prompt §31-32)."""

from __future__ import annotations

import sqlite3

import pytest

from backend.application.loyalty_cards.authorization import LoyaltyCardsAuthorizationPolicy
from backend.application.loyalty_cards.use_cases.card_use_cases import (
    ActivateLoyaltyCardUseCase,
    BlockLoyaltyCardUseCase,
    CancelLoyaltyCardUseCase,
    IssueLoyaltyCardUseCase,
    ReplaceLoyaltyCardUseCase,
    UnblockLoyaltyCardUseCase,
)
from backend.application.loyalty_cards.use_cases.token_use_cases import (
    RotateLoyaltyCardTokenUseCase,
)
from backend.domain.loyalty_cards.enums import LoyaltyCardType
from backend.infrastructure.db.repositories.loyalty_cards.unit_of_work import (
    LoyaltyCardsUnitOfWork,
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


def _issue(conn, auth):
    return IssueLoyaltyCardUseCase(auth).execute(
        conn, customer_id=new_uuid(), membership_id=new_uuid(), card_type=LoyaltyCardType.PHYSICAL,
        actor_user_id=new_uuid(), actor_branch_id=new_uuid(), operation_id=new_uuid())


class TestIssueAndActivate:
    def test_issue_creates_card_and_token(self, conn, auth):
        result = _issue(conn, auth)
        assert result.success
        assert result.data["card_number"] == "LC-00000001"
        assert result.data["token"]

    def test_second_card_gets_sequential_number(self, conn, auth):
        _issue(conn, auth)
        result = _issue(conn, auth)
        assert result.data["card_number"] == "LC-00000002"

    def test_activate(self, conn, auth):
        issued = _issue(conn, auth)
        result = ActivateLoyaltyCardUseCase(auth).execute(
            conn, card_id=issued.entity_id, actor_user_id=new_uuid(),
            actor_branch_id=new_uuid(), operation_id=new_uuid())
        assert result.success

    def test_card_not_found(self, conn, auth):
        result = ActivateLoyaltyCardUseCase(auth).execute(
            conn, card_id=new_uuid(), actor_user_id=new_uuid(), actor_branch_id=new_uuid(),
            operation_id=new_uuid())
        assert not result.success
        assert result.error_code == "CARD_NOT_FOUND"


class TestBlockUnblock:
    def test_block_revokes_active_token(self, conn, auth):
        issued = _issue(conn, auth)
        ActivateLoyaltyCardUseCase(auth).execute(
            conn, card_id=issued.entity_id, actor_user_id=new_uuid(),
            actor_branch_id=new_uuid(), operation_id=new_uuid())
        result = BlockLoyaltyCardUseCase(auth).execute(
            conn, card_id=issued.entity_id, reason="reportada perdida", actor_user_id=new_uuid(),
            actor_branch_id=new_uuid(), operation_id=new_uuid())
        assert result.success
        with LoyaltyCardsUnitOfWork(conn) as uow:
            token = uow.tokens.get_active_for_card(issued.entity_id)
            assert token is None

    def test_unblock_issues_fresh_token(self, conn, auth):
        issued = _issue(conn, auth)
        ActivateLoyaltyCardUseCase(auth).execute(
            conn, card_id=issued.entity_id, actor_user_id=new_uuid(),
            actor_branch_id=new_uuid(), operation_id=new_uuid())
        BlockLoyaltyCardUseCase(auth).execute(
            conn, card_id=issued.entity_id, reason="motivo", actor_user_id=new_uuid(),
            actor_branch_id=new_uuid(), operation_id=new_uuid())
        result = UnblockLoyaltyCardUseCase(auth).execute(
            conn, card_id=issued.entity_id, actor_user_id=new_uuid(),
            actor_branch_id=new_uuid(), operation_id=new_uuid())
        assert result.success
        assert result.data["token"] != issued.data["token"]


class TestReplace:
    def test_replace_creates_new_card_and_revokes_old_token(self, conn, auth):
        issued = _issue(conn, auth)
        ActivateLoyaltyCardUseCase(auth).execute(
            conn, card_id=issued.entity_id, actor_user_id=new_uuid(),
            actor_branch_id=new_uuid(), operation_id=new_uuid())
        result = ReplaceLoyaltyCardUseCase(auth).execute(
            conn, card_id=issued.entity_id, actor_user_id=new_uuid(),
            actor_branch_id=new_uuid(), operation_id=new_uuid())
        assert result.success
        assert result.entity_id != issued.entity_id
        with LoyaltyCardsUnitOfWork(conn) as uow:
            old_card = uow.cards.get(issued.entity_id)
            assert old_card.status.value == "REPLACED"
            assert old_card.replaced_by_card_id == result.entity_id
            new_card = uow.cards.get(result.entity_id)
            assert new_card.replaces_card_id == issued.entity_id
            assert uow.tokens.get_active_for_card(issued.entity_id) is None
            assert uow.tokens.get_active_for_card(result.entity_id) is not None


class TestCancel:
    def test_cancel_revokes_token(self, conn, auth):
        issued = _issue(conn, auth)
        result = CancelLoyaltyCardUseCase(auth).execute(
            conn, card_id=issued.entity_id, reason="cliente se dio de baja",
            actor_user_id=new_uuid(), actor_branch_id=new_uuid(), operation_id=new_uuid())
        assert result.success
        with LoyaltyCardsUnitOfWork(conn) as uow:
            assert uow.tokens.get_active_for_card(issued.entity_id) is None


class TestRotateToken:
    def test_rotate(self, conn, auth):
        issued = _issue(conn, auth)
        result = RotateLoyaltyCardTokenUseCase(auth).execute(
            conn, card_id=issued.entity_id, actor_user_id=new_uuid(),
            actor_branch_id=new_uuid(), operation_id=new_uuid())
        assert result.success
        assert result.data["token"] != issued.data["token"]
        with LoyaltyCardsUnitOfWork(conn) as uow:
            active = uow.tokens.get_active_for_card(issued.entity_id)
            assert active.token == result.data["token"]

    def test_rotate_requires_existing_active_token(self, conn, auth):
        issued = _issue(conn, auth)
        RotateLoyaltyCardTokenUseCase(auth).execute(
            conn, card_id=issued.entity_id, actor_user_id=new_uuid(),
            actor_branch_id=new_uuid(), operation_id=new_uuid())
        with LoyaltyCardsUnitOfWork(conn) as uow:
            active = uow.tokens.get_active_for_card(issued.entity_id)
            active.revoke()
            uow.tokens.save(active)
        result = RotateLoyaltyCardTokenUseCase(auth).execute(
            conn, card_id=issued.entity_id, actor_user_id=new_uuid(),
            actor_branch_id=new_uuid(), operation_id=new_uuid())
        assert not result.success
        assert result.error_code == "TOKEN_NOT_FOUND"
