"""LeadQualificationRepository — persists qualification evidence records."""

from __future__ import annotations

import json

from backend.domain.crm.entities.lead_qualification import LeadQualification
from backend.domain.crm.enums import QualificationDecision, QualificationModel
from backend.infrastructure.db.repositories.crm.base import CRMRepositoryBase

_COLS = (
    "id, lead_id, model, decision, qualified_by_user_id, criteria_json, notes,"
    " score, created_at"
)


class LeadQualificationRepository(CRMRepositoryBase):
    def save(self, qualification: LeadQualification) -> None:
        self._execute(
            f"INSERT INTO lead_qualifications ({_COLS}) VALUES (?,?,?,?,?,?,?,?,?)",
            (qualification.id, qualification.lead_id, qualification.model.value,
             qualification.decision.value, qualification.qualified_by_user_id,
             json.dumps(qualification.criteria), qualification.notes,
             qualification.score, qualification.created_at))

    def list_for_lead(self, lead_id: str) -> list[LeadQualification]:
        rows = self._query(
            f"SELECT {_COLS} FROM lead_qualifications WHERE lead_id=?"
            " ORDER BY created_at DESC", (lead_id,))
        return [self._hydrate(r) for r in rows]

    @staticmethod
    def _hydrate(row: dict) -> LeadQualification:
        return LeadQualification(
            id=row["id"], lead_id=row["lead_id"], model=QualificationModel(row["model"]),
            decision=QualificationDecision(row["decision"]),
            qualified_by_user_id=row["qualified_by_user_id"],
            criteria=json.loads(row["criteria_json"] or "{}"), notes=row["notes"] or "",
            score=row["score"], created_at=row["created_at"],
        )
