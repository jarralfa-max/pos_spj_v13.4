"""LoyaltyCardRepository / LoyaltyCardTokenRepository — persist/reconstruct
LoyaltyCard and LoyaltyCardPublicToken (LOY-16, §31-32)."""

from __future__ import annotations

from backend.domain.loyalty_cards.entities.loyalty_card import LoyaltyCard
from backend.domain.loyalty_cards.entities.loyalty_card_token import LoyaltyCardPublicToken
from backend.domain.loyalty_cards.enums import LoyaltyCardStatus, LoyaltyCardTokenStatus, LoyaltyCardType
from backend.infrastructure.db.repositories.loyalty_cards.base import LoyaltyCardsRepositoryBase


class LoyaltyCardRepository(LoyaltyCardsRepositoryBase):
    def save(self, card: LoyaltyCard) -> None:
        self._execute(
            """
            INSERT INTO loyalty_cards (
                id, card_number, card_type, customer_id, membership_id, status, issued_at,
                activated_at, blocked_at, block_reason, replaces_card_id, replaced_by_card_id,
                cancelled_at, cancel_reason, expires_at, created_at, updated_at
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            ON CONFLICT(id) DO UPDATE SET
                status=excluded.status,
                activated_at=excluded.activated_at,
                blocked_at=excluded.blocked_at,
                block_reason=excluded.block_reason,
                replaces_card_id=excluded.replaces_card_id,
                replaced_by_card_id=excluded.replaced_by_card_id,
                cancelled_at=excluded.cancelled_at,
                cancel_reason=excluded.cancel_reason,
                expires_at=excluded.expires_at,
                updated_at=excluded.updated_at
            """,
            (
                card.id, card.card_number, card.card_type.value, card.customer_id,
                card.membership_id, card.status.value, card.issued_at, card.activated_at,
                card.blocked_at, card.block_reason, card.replaces_card_id,
                card.replaced_by_card_id, card.cancelled_at, card.cancel_reason,
                card.expires_at, card.created_at, card.updated_at,
            ),
        )

    def get(self, card_id: str) -> LoyaltyCard | None:
        row = self._query_one("SELECT * FROM loyalty_cards WHERE id=?", (card_id,))
        return self._hydrate(row) if row else None

    def get_by_number(self, card_number: str) -> LoyaltyCard | None:
        row = self._query_one("SELECT * FROM loyalty_cards WHERE card_number=?", (card_number,))
        return self._hydrate(row) if row else None

    def list_for_customer(self, customer_id: str) -> list[LoyaltyCard]:
        rows = self._query(
            "SELECT * FROM loyalty_cards WHERE customer_id=? ORDER BY created_at",
            (customer_id,))
        return [self._hydrate(row) for row in rows]

    def count_all(self) -> int:
        return self._scalar("SELECT COUNT(*) FROM loyalty_cards", (), default=0)

    def count_for_membership(self, membership_id: str) -> int:
        return self._scalar(
            "SELECT COUNT(*) FROM loyalty_cards WHERE membership_id=?",
            (membership_id,), default=0)

    @staticmethod
    def _hydrate(row: dict) -> LoyaltyCard:
        return LoyaltyCard(
            id=row["id"], card_number=row["card_number"],
            card_type=LoyaltyCardType(row["card_type"]), customer_id=row["customer_id"],
            membership_id=row["membership_id"], status=LoyaltyCardStatus(row["status"]),
            issued_at=row["issued_at"], activated_at=row["activated_at"],
            blocked_at=row["blocked_at"], block_reason=row["block_reason"],
            replaces_card_id=row["replaces_card_id"],
            replaced_by_card_id=row["replaced_by_card_id"], cancelled_at=row["cancelled_at"],
            cancel_reason=row["cancel_reason"], expires_at=row["expires_at"],
            created_at=row["created_at"], updated_at=row["updated_at"],
        )


class LoyaltyCardTokenRepository(LoyaltyCardsRepositoryBase):
    def save(self, token: LoyaltyCardPublicToken) -> None:
        self._execute(
            """
            INSERT INTO loyalty_card_tokens (
                id, card_id, token, status, created_at, rotated_at, revoked_at
            ) VALUES (?,?,?,?,?,?,?)
            ON CONFLICT(id) DO UPDATE SET
                status=excluded.status,
                rotated_at=excluded.rotated_at,
                revoked_at=excluded.revoked_at
            """,
            (token.id, token.card_id, token.token, token.status.value, token.created_at,
             token.rotated_at, token.revoked_at),
        )

    def get(self, token_id: str) -> LoyaltyCardPublicToken | None:
        row = self._query_one("SELECT * FROM loyalty_card_tokens WHERE id=?", (token_id,))
        return self._hydrate(row) if row else None

    def get_by_token(self, token: str) -> LoyaltyCardPublicToken | None:
        row = self._query_one("SELECT * FROM loyalty_card_tokens WHERE token=?", (token,))
        return self._hydrate(row) if row else None

    def get_active_for_card(self, card_id: str) -> LoyaltyCardPublicToken | None:
        row = self._query_one(
            "SELECT * FROM loyalty_card_tokens WHERE card_id=? AND status='ACTIVE'",
            (card_id,))
        return self._hydrate(row) if row else None

    @staticmethod
    def _hydrate(row: dict) -> LoyaltyCardPublicToken:
        return LoyaltyCardPublicToken(
            id=row["id"], card_id=row["card_id"], token=row["token"],
            status=LoyaltyCardTokenStatus(row["status"]), created_at=row["created_at"],
            rotated_at=row["rotated_at"], revoked_at=row["revoked_at"],
        )
