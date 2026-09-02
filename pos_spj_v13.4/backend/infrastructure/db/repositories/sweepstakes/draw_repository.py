"""DrawRepository / WinnerRepository — persist/reconstruct SweepstakesDraw
and SweepstakesWinner (LOY-15, §27)."""

from __future__ import annotations

from backend.domain.sweepstakes.entities.sweepstakes_draw import SweepstakesDraw
from backend.domain.sweepstakes.entities.sweepstakes_winner import SweepstakesWinner
from backend.domain.sweepstakes.enums import SweepstakesDrawStatus, SweepstakesWinnerStatus
from backend.infrastructure.db.repositories.sweepstakes.base import SweepstakesRepositoryBase


class SweepstakesDrawRepository(SweepstakesRepositoryBase):
    def save(self, draw: SweepstakesDraw) -> None:
        self._execute(
            """
            INSERT INTO sweepstakes_draws (
                id, campaign_id, status, scheduled_at, executed_at, executed_by_user_id,
                random_seed, pool_hash, ticket_pool_size, created_at
            ) VALUES (?,?,?,?,?,?,?,?,?,?)
            ON CONFLICT(id) DO UPDATE SET
                status=excluded.status,
                executed_at=excluded.executed_at,
                executed_by_user_id=excluded.executed_by_user_id,
                random_seed=excluded.random_seed,
                pool_hash=excluded.pool_hash,
                ticket_pool_size=excluded.ticket_pool_size
            """,
            (
                draw.id, draw.campaign_id, draw.status.value, draw.scheduled_at,
                draw.executed_at, draw.executed_by_user_id, draw.random_seed, draw.pool_hash,
                draw.ticket_pool_size, draw.created_at,
            ),
        )

    def get(self, draw_id: str) -> SweepstakesDraw | None:
        row = self._query_one("SELECT * FROM sweepstakes_draws WHERE id=?", (draw_id,))
        return self._hydrate(row) if row else None

    def list_for_campaign(self, campaign_id: str) -> list[SweepstakesDraw]:
        rows = self._query(
            "SELECT * FROM sweepstakes_draws WHERE campaign_id=? ORDER BY created_at",
            (campaign_id,))
        return [self._hydrate(row) for row in rows]

    @staticmethod
    def _hydrate(row: dict) -> SweepstakesDraw:
        return SweepstakesDraw(
            id=row["id"], campaign_id=row["campaign_id"],
            status=SweepstakesDrawStatus(row["status"]), scheduled_at=row["scheduled_at"],
            executed_at=row["executed_at"], executed_by_user_id=row["executed_by_user_id"],
            random_seed=row["random_seed"], pool_hash=row["pool_hash"],
            ticket_pool_size=row["ticket_pool_size"], created_at=row["created_at"],
        )


class SweepstakesWinnerRepository(SweepstakesRepositoryBase):
    def save(self, winner: SweepstakesWinner) -> None:
        self._execute(
            """
            INSERT INTO sweepstakes_winners (
                id, draw_id, campaign_id, ticket_id, customer_id, prize_id, rank, status,
                selected_at, validated_at, validated_by_user_id, disqualification_reason,
                delivered_at, delivered_by_user_id
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            ON CONFLICT(id) DO UPDATE SET
                status=excluded.status,
                validated_at=excluded.validated_at,
                validated_by_user_id=excluded.validated_by_user_id,
                disqualification_reason=excluded.disqualification_reason,
                delivered_at=excluded.delivered_at,
                delivered_by_user_id=excluded.delivered_by_user_id
            """,
            (
                winner.id, winner.draw_id, winner.campaign_id, winner.ticket_id,
                winner.customer_id, winner.prize_id, winner.rank, winner.status.value,
                winner.selected_at, winner.validated_at, winner.validated_by_user_id,
                winner.disqualification_reason, winner.delivered_at, winner.delivered_by_user_id,
            ),
        )

    def get(self, winner_id: str) -> SweepstakesWinner | None:
        row = self._query_one("SELECT * FROM sweepstakes_winners WHERE id=?", (winner_id,))
        return self._hydrate(row) if row else None

    def list_for_draw(self, draw_id: str) -> list[SweepstakesWinner]:
        rows = self._query(
            "SELECT * FROM sweepstakes_winners WHERE draw_id=? ORDER BY rank", (draw_id,))
        return [self._hydrate(row) for row in rows]

    def list_ticket_ids_won_in_campaign(self, campaign_id: str) -> frozenset[str]:
        rows = self._query(
            "SELECT ticket_id FROM sweepstakes_winners WHERE campaign_id=?"
            " AND status != 'DISQUALIFIED'", (campaign_id,))
        return frozenset(row["ticket_id"] for row in rows)

    @staticmethod
    def _hydrate(row: dict) -> SweepstakesWinner:
        return SweepstakesWinner(
            id=row["id"], draw_id=row["draw_id"], campaign_id=row["campaign_id"],
            ticket_id=row["ticket_id"], customer_id=row["customer_id"], prize_id=row["prize_id"],
            rank=row["rank"], status=SweepstakesWinnerStatus(row["status"]),
            selected_at=row["selected_at"], validated_at=row["validated_at"],
            validated_by_user_id=row["validated_by_user_id"],
            disqualification_reason=row["disqualification_reason"],
            delivered_at=row["delivered_at"], delivered_by_user_id=row["delivered_by_user_id"],
        )
