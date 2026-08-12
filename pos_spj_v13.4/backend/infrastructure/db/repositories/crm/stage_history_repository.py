"""OpportunityStageHistoryRepository — append-only log of stage moves."""

from __future__ import annotations

from datetime import date

from backend.domain.crm.entities.opportunity_stage_history import OpportunityStageHistory
from backend.infrastructure.db.repositories.crm.base import CRMRepositoryBase

_HISTORY_COLS = (
    "id, opportunity_id, from_stage_id, to_stage_id, changed_by_user_id,"
    " reason, probability, expected_close_date, created_at"
)


class OpportunityStageHistoryRepository(CRMRepositoryBase):
    def save(self, history: OpportunityStageHistory) -> None:
        self._execute(
            f"INSERT INTO opportunity_stage_history ({_HISTORY_COLS})"
            " VALUES (?,?,?,?,?,?,?,?,?)",
            (history.id, history.opportunity_id, history.from_stage_id, history.to_stage_id,
             history.changed_by_user_id, history.reason, history.probability,
             history.expected_close_date.isoformat() if history.expected_close_date else None,
             history.created_at))

    def list_for_opportunity(self, opportunity_id: str) -> list[OpportunityStageHistory]:
        rows = self._query(
            f"SELECT {_HISTORY_COLS} FROM opportunity_stage_history"
            " WHERE opportunity_id=? ORDER BY created_at ASC", (opportunity_id,))
        return [self._hydrate(r) for r in rows]

    @staticmethod
    def _hydrate(row: dict) -> OpportunityStageHistory:
        return OpportunityStageHistory(
            id=row["id"], opportunity_id=row["opportunity_id"],
            to_stage_id=row["to_stage_id"], changed_by_user_id=row["changed_by_user_id"],
            from_stage_id=row["from_stage_id"], reason=row["reason"] or "",
            probability=row["probability"],
            expected_close_date=(date.fromisoformat(row["expected_close_date"])
                                 if row["expected_close_date"] else None),
            created_at=row["created_at"],
        )
