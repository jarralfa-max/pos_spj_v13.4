"""LoyaltyCardPrintJobRepository — persist/reconstruct LoyaltyCardPrintJob
(LOY-22, §50-51)."""

from __future__ import annotations

from backend.domain.loyalty_cards.entities.loyalty_card_print_job import LoyaltyCardPrintJob
from backend.domain.loyalty_cards.enums import LoyaltyCardPrintJobStatus
from backend.infrastructure.db.repositories.loyalty_cards.base import LoyaltyCardsRepositoryBase


class LoyaltyCardPrintJobRepository(LoyaltyCardsRepositoryBase):
    def save(self, job: LoyaltyCardPrintJob) -> None:
        self._execute(
            """
            INSERT INTO loyalty_card_print_jobs (
                id, batch_id, requested_by_user_id, only_sheet_number, status, failure_reason,
                reprint_of_job_id, reprint_reason, requested_at, rendered_at, created_at,
                updated_at
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
            ON CONFLICT(id) DO UPDATE SET
                status=excluded.status,
                failure_reason=excluded.failure_reason,
                rendered_at=excluded.rendered_at,
                updated_at=excluded.updated_at
            """,
            (
                job.id, job.batch_id, job.requested_by_user_id, job.only_sheet_number,
                job.status.value, job.failure_reason, job.reprint_of_job_id, job.reprint_reason,
                job.requested_at, job.rendered_at, job.created_at, job.updated_at,
            ),
        )

    def get(self, job_id: str) -> LoyaltyCardPrintJob | None:
        row = self._query_one("SELECT * FROM loyalty_card_print_jobs WHERE id=?", (job_id,))
        return self._hydrate(row) if row else None

    def list_for_batch(self, batch_id: str) -> list[LoyaltyCardPrintJob]:
        rows = self._query(
            "SELECT * FROM loyalty_card_print_jobs WHERE batch_id=? ORDER BY requested_at",
            (batch_id,))
        return [self._hydrate(row) for row in rows]

    @staticmethod
    def _hydrate(row: dict) -> LoyaltyCardPrintJob:
        return LoyaltyCardPrintJob(
            id=row["id"], batch_id=row["batch_id"],
            requested_by_user_id=row["requested_by_user_id"],
            only_sheet_number=row["only_sheet_number"],
            status=LoyaltyCardPrintJobStatus(row["status"]), failure_reason=row["failure_reason"],
            reprint_of_job_id=row["reprint_of_job_id"], reprint_reason=row["reprint_reason"],
            requested_at=row["requested_at"], rendered_at=row["rendered_at"],
            created_at=row["created_at"], updated_at=row["updated_at"],
        )
