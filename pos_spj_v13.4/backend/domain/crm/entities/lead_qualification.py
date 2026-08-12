"""LeadQualification — the evidence a qualification decision leaves behind
(§17: "La calificación debe dejar evidencia").

``criteria`` is a free-form mapping (never a fixed set of columns) because
§17 explicitly forbids hardcoding one qualification methodology: a MANUAL
decision might record free-text notes per axis (necesidad, presupuesto,
autoridad de compra, tiempo esperado, zona de atención, tipo de cliente,
volumen esperado, productos de interés, capacidad de crédito,
consentimiento — the axes §17 names as examples, not a mandatory schema);
a SCORE_BASED or BANT_LIKE model might record numeric sub-scores instead.
This entity only guarantees the record exists, who made the call, under
which model, and why — not what shape the criteria take.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

from backend.domain.crm.enums import QualificationDecision, QualificationModel
from backend.domain.crm.exceptions import LeadQualificationFailedError
from backend.shared.ids import new_uuid


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass(slots=True)
class LeadQualification:
    id: str
    lead_id: str
    model: QualificationModel
    decision: QualificationDecision
    qualified_by_user_id: str
    criteria: dict = field(default_factory=dict)
    notes: str = ""
    score: int | None = None
    created_at: str = field(default_factory=_utcnow)

    @classmethod
    def create(
        cls, lead_id: str, model: QualificationModel, decision: QualificationDecision,
        qualified_by_user_id: str, *, criteria: dict | None = None, notes: str = "",
        score: int | None = None,
    ) -> "LeadQualification":
        if not lead_id:
            raise LeadQualificationFailedError("LeadQualification requiere lead_id")
        if not qualified_by_user_id:
            raise LeadQualificationFailedError(
                "LeadQualification requiere quién calificó (qualified_by_user_id)")
        if model is QualificationModel.SCORE_BASED and score is None:
            raise LeadQualificationFailedError(
                "El modelo SCORE_BASED requiere un score")
        if model in (QualificationModel.BANT_LIKE, QualificationModel.CUSTOM_RULE) \
                and not (criteria or {}):
            raise LeadQualificationFailedError(
                f"El modelo {model.value} requiere al menos un criterio evaluado")
        return cls(
            id=new_uuid(), lead_id=lead_id, model=model, decision=decision,
            qualified_by_user_id=qualified_by_user_id, criteria=dict(criteria or {}),
            notes=notes, score=score,
        )
