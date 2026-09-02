"""LoyaltyDigitalCardProjectionRepository — persist/reconstruct
LoyaltyDigitalCardProjection (LOY-23, §48)."""

from __future__ import annotations

import json

from backend.domain.loyalty_cards.entities.loyalty_digital_card_projection import (
    LoyaltyDigitalCardProjection,
)
from backend.infrastructure.db.repositories.loyalty_cards.base import LoyaltyCardsRepositoryBase


class LoyaltyDigitalCardProjectionRepository(LoyaltyCardsRepositoryBase):
    def save(self, projection: LoyaltyDigitalCardProjection) -> None:
        self._execute(
            """
            INSERT INTO loyalty_digital_card_projections (
                id, card_id, customer_id, card_number, qr_token, display_fields_json,
                last_refreshed_at, created_at
            ) VALUES (?,?,?,?,?,?,?,?)
            ON CONFLICT(id) DO UPDATE SET
                qr_token=excluded.qr_token,
                display_fields_json=excluded.display_fields_json,
                last_refreshed_at=excluded.last_refreshed_at
            """,
            (
                projection.id, projection.card_id, projection.customer_id,
                projection.card_number, projection.qr_token,
                json.dumps(projection.display_fields, ensure_ascii=False),
                projection.last_refreshed_at, projection.created_at,
            ),
        )

    def get(self, projection_id: str) -> LoyaltyDigitalCardProjection | None:
        row = self._query_one(
            "SELECT * FROM loyalty_digital_card_projections WHERE id=?", (projection_id,))
        return self._hydrate(row) if row else None

    def get_by_card(self, card_id: str) -> LoyaltyDigitalCardProjection | None:
        row = self._query_one(
            "SELECT * FROM loyalty_digital_card_projections WHERE card_id=?", (card_id,))
        return self._hydrate(row) if row else None

    def list_for_customer(self, customer_id: str) -> list[LoyaltyDigitalCardProjection]:
        rows = self._query(
            "SELECT * FROM loyalty_digital_card_projections WHERE customer_id=?"
            " ORDER BY created_at", (customer_id,))
        return [self._hydrate(row) for row in rows]

    @staticmethod
    def _hydrate(row: dict) -> LoyaltyDigitalCardProjection:
        return LoyaltyDigitalCardProjection(
            id=row["id"], card_id=row["card_id"], customer_id=row["customer_id"],
            card_number=row["card_number"], qr_token=row["qr_token"],
            display_fields=json.loads(row["display_fields_json"]),
            last_refreshed_at=row["last_refreshed_at"], created_at=row["created_at"],
        )
