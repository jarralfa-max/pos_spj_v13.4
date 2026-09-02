"""LoyaltyCardBatchRepository / LoyaltyCardBatchItemRepository —
persist/reconstruct batches + batch items (LOY-21, §43-44)."""

from __future__ import annotations

from backend.domain.loyalty_cards.entities.loyalty_card_batch import LoyaltyCardBatch
from backend.domain.loyalty_cards.entities.loyalty_card_batch_item import LoyaltyCardBatchItem
from backend.domain.loyalty_cards.enums import LoyaltyCardBatchItemStatus, LoyaltyCardBatchStatus
from backend.infrastructure.db.repositories.loyalty_cards.base import LoyaltyCardsRepositoryBase


class LoyaltyCardBatchRepository(LoyaltyCardsRepositoryBase):
    def save(self, batch: LoyaltyCardBatch) -> None:
        self._execute(
            """
            INSERT INTO loyalty_card_batches (
                id, template_id, imposition_profile_id, item_count, cards_per_sheet, status,
                created_by_user_id, approved_by_user_id, created_at, updated_at
            ) VALUES (?,?,?,?,?,?,?,?,?,?)
            ON CONFLICT(id) DO UPDATE SET
                status=excluded.status,
                approved_by_user_id=excluded.approved_by_user_id,
                updated_at=excluded.updated_at
            """,
            (
                batch.id, batch.template_id, batch.imposition_profile_id, batch.item_count,
                batch.cards_per_sheet, batch.status.value, batch.created_by_user_id,
                batch.approved_by_user_id, batch.created_at, batch.updated_at,
            ),
        )

    def get(self, batch_id: str) -> LoyaltyCardBatch | None:
        row = self._query_one("SELECT * FROM loyalty_card_batches WHERE id=?", (batch_id,))
        return self._hydrate(row) if row else None

    @staticmethod
    def _hydrate(row: dict) -> LoyaltyCardBatch:
        return LoyaltyCardBatch(
            id=row["id"], template_id=row["template_id"],
            imposition_profile_id=row["imposition_profile_id"], item_count=row["item_count"],
            cards_per_sheet=row["cards_per_sheet"], status=LoyaltyCardBatchStatus(row["status"]),
            created_by_user_id=row["created_by_user_id"],
            approved_by_user_id=row["approved_by_user_id"], created_at=row["created_at"],
            updated_at=row["updated_at"],
        )


class LoyaltyCardBatchItemRepository(LoyaltyCardsRepositoryBase):
    def save(self, item: LoyaltyCardBatchItem) -> None:
        self._execute(
            """
            INSERT INTO loyalty_card_batch_items (
                id, batch_id, card_id, sheet_number, position_in_sheet, status,
                failure_reason, printed_at, created_at
            ) VALUES (?,?,?,?,?,?,?,?,?)
            ON CONFLICT(id) DO UPDATE SET
                status=excluded.status,
                failure_reason=excluded.failure_reason,
                printed_at=excluded.printed_at
            """,
            (
                item.id, item.batch_id, item.card_id, item.sheet_number, item.position_in_sheet,
                item.status.value, item.failure_reason, item.printed_at, item.created_at,
            ),
        )

    def get(self, item_id: str) -> LoyaltyCardBatchItem | None:
        row = self._query_one("SELECT * FROM loyalty_card_batch_items WHERE id=?", (item_id,))
        return self._hydrate(row) if row else None

    def list_for_batch(self, batch_id: str) -> list[LoyaltyCardBatchItem]:
        rows = self._query(
            "SELECT * FROM loyalty_card_batch_items WHERE batch_id=?"
            " ORDER BY sheet_number, position_in_sheet", (batch_id,))
        return [self._hydrate(row) for row in rows]

    def count_for_batch(self, batch_id: str) -> int:
        return self._scalar(
            "SELECT COUNT(*) FROM loyalty_card_batch_items WHERE batch_id=?",
            (batch_id,), default=0)

    def count_pending_for_batch(self, batch_id: str) -> int:
        return self._scalar(
            "SELECT COUNT(*) FROM loyalty_card_batch_items WHERE batch_id=? AND status='PENDING'",
            (batch_id,), default=0)

    @staticmethod
    def _hydrate(row: dict) -> LoyaltyCardBatchItem:
        return LoyaltyCardBatchItem(
            id=row["id"], batch_id=row["batch_id"], card_id=row["card_id"],
            sheet_number=row["sheet_number"], position_in_sheet=row["position_in_sheet"],
            status=LoyaltyCardBatchItemStatus(row["status"]),
            failure_reason=row["failure_reason"], printed_at=row["printed_at"],
            created_at=row["created_at"],
        )
