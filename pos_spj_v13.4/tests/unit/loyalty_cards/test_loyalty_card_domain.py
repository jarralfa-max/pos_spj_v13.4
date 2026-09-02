"""LOY-16 — Loyalty Card / LoyaltyCardPublicToken domain entities (master
prompt §31-32)."""

from __future__ import annotations

import pytest

from backend.domain.loyalty_cards.entities.loyalty_card import LoyaltyCard
from backend.domain.loyalty_cards.entities.loyalty_card_token import LoyaltyCardPublicToken
from backend.domain.loyalty_cards.enums import LoyaltyCardType
from backend.domain.loyalty_cards.exceptions import (
    InvalidLoyaltyCardError,
    InvalidLoyaltyCardStateError,
    InvalidLoyaltyCardTokenStateError,
)
from backend.shared.ids import new_uuid


def _issue_card() -> LoyaltyCard:
    return LoyaltyCard.issue("LC-00000001", LoyaltyCardType.PHYSICAL, new_uuid(), new_uuid())


class TestLoyaltyCard:
    def test_requires_customer_and_membership(self):
        with pytest.raises(InvalidLoyaltyCardError):
            LoyaltyCard.issue("LC-1", LoyaltyCardType.PHYSICAL, "", new_uuid())

    def test_issue_starts_as_issued(self):
        card = _issue_card()
        assert card.status.value == "ISSUED"
        assert not card.is_usable()

    def test_activate_then_usable(self):
        card = _issue_card()
        card.activate()
        assert card.status.value == "ACTIVE"
        assert card.is_usable()

    def test_cannot_activate_twice(self):
        card = _issue_card()
        card.activate()
        with pytest.raises(InvalidLoyaltyCardStateError):
            card.activate()

    def test_block_requires_active(self):
        card = _issue_card()
        with pytest.raises(InvalidLoyaltyCardStateError):
            card.block("perdida")

    def test_block_then_unblock(self):
        card = _issue_card()
        card.activate()
        card.block("perdida")
        assert card.status.value == "BLOCKED"
        card.unblock()
        assert card.status.value == "ACTIVE"
        assert card.block_reason is None

    def test_block_requires_reason(self):
        card = _issue_card()
        card.activate()
        with pytest.raises(InvalidLoyaltyCardStateError):
            card.block("")

    def test_replacement_links_both_ways(self):
        old_card = _issue_card()
        old_card.activate()
        new_card = LoyaltyCard.issue_replacement(old_card, "LC-00000002")
        old_card.mark_replaced(new_card.id)
        assert old_card.status.value == "REPLACED"
        assert old_card.replaced_by_card_id == new_card.id
        assert new_card.replaces_card_id == old_card.id
        assert new_card.customer_id == old_card.customer_id
        assert new_card.membership_id == old_card.membership_id

    def test_cannot_replace_cancelled_card(self):
        card = _issue_card()
        card.activate()
        card.cancel("cliente se dio de baja")
        with pytest.raises(InvalidLoyaltyCardStateError):
            card.mark_replaced(new_uuid())

    def test_cancel_requires_reason(self):
        card = _issue_card()
        with pytest.raises(InvalidLoyaltyCardStateError):
            card.cancel("")

    def test_expire_only_from_issued_or_active(self):
        card = _issue_card()
        card.activate()
        card.cancel("motivo")
        with pytest.raises(InvalidLoyaltyCardStateError):
            card.expire()


class TestLoyaltyCardPublicToken:
    def test_issue_creates_active_token(self):
        token = LoyaltyCardPublicToken.issue(new_uuid())
        assert token.status.value == "ACTIVE"
        assert token.is_usable()
        assert len(token.token) > 10

    def test_rotate_deactivates_old_and_creates_new(self):
        old_token = LoyaltyCardPublicToken.issue(new_uuid())
        new_token = old_token.rotate()
        assert old_token.status.value == "ROTATED"
        assert not old_token.is_usable()
        assert new_token.status.value == "ACTIVE"
        assert new_token.card_id == old_token.card_id
        assert new_token.token != old_token.token

    def test_cannot_rotate_twice(self):
        token = LoyaltyCardPublicToken.issue(new_uuid())
        token.rotate()
        with pytest.raises(InvalidLoyaltyCardTokenStateError):
            token.rotate()

    def test_revoke(self):
        token = LoyaltyCardPublicToken.issue(new_uuid())
        token.revoke()
        assert token.status.value == "REVOKED"
        assert not token.is_usable()

    def test_cannot_revoke_twice(self):
        token = LoyaltyCardPublicToken.issue(new_uuid())
        token.revoke()
        with pytest.raises(InvalidLoyaltyCardTokenStateError):
            token.revoke()
