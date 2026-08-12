"""LeadQualificationPolicy — decides QUALIFIED/UNQUALIFIED without
hardcoding one methodology (§17).

Each ``QualificationModel`` gets its own decision rule, all configuration-
driven (no fixed thresholds baked in):

- ``MANUAL`` — the human's decision is authoritative; the policy only
  requires one was actually supplied.
- ``SCORE_BASED`` — qualified iff ``score >= threshold`` (``threshold``
  comes from the caller/``ModuleSettingsService``, never hardcoded here —
  see CLAUDE.md §22-24 on arbitrary UI defaults).
- ``BANT_LIKE`` — qualified iff at least ``min_criteria_passed`` of the
  supplied criteria evaluate truthy (Budget/Authority/Need/Timeline-style:
  the caller decides which axes to send, this policy only counts).
- ``CUSTOM_RULE`` — the caller has already run their own rule and hands the
  decision in; the policy only enforces that qualification evidence
  (``criteria``) was actually recorded, matching what
  ``LeadQualification.create()`` already requires for this model.

Pure domain logic — no I/O, never touches a repository.
"""

from __future__ import annotations

from backend.domain.crm.enums import QualificationDecision, QualificationModel
from backend.domain.crm.exceptions import LeadQualificationFailedError


class LeadQualificationPolicy:
    def decide(
        self, model: QualificationModel, *, criteria: dict | None = None,
        score: int | None = None, score_threshold: int | None = None,
        min_criteria_passed: int | None = None,
        manual_decision: QualificationDecision | None = None,
        custom_decision: QualificationDecision | None = None,
    ) -> QualificationDecision:
        criteria = criteria or {}

        if model is QualificationModel.MANUAL:
            if manual_decision is None:
                raise LeadQualificationFailedError(
                    "El modelo MANUAL requiere una decisión explícita del usuario")
            return manual_decision

        if model is QualificationModel.SCORE_BASED:
            if score is None or score_threshold is None:
                raise LeadQualificationFailedError(
                    "El modelo SCORE_BASED requiere score y score_threshold")
            return (QualificationDecision.QUALIFIED if score >= score_threshold
                    else QualificationDecision.UNQUALIFIED)

        if model is QualificationModel.BANT_LIKE:
            if not criteria:
                raise LeadQualificationFailedError(
                    "El modelo BANT_LIKE requiere al menos un criterio evaluado")
            threshold = min_criteria_passed if min_criteria_passed is not None else len(criteria)
            passed = sum(1 for value in criteria.values() if value)
            return (QualificationDecision.QUALIFIED if passed >= threshold
                    else QualificationDecision.UNQUALIFIED)

        if model is QualificationModel.CUSTOM_RULE:
            if not criteria:
                raise LeadQualificationFailedError(
                    "El modelo CUSTOM_RULE requiere criterios como evidencia")
            if custom_decision is None:
                raise LeadQualificationFailedError(
                    "El modelo CUSTOM_RULE requiere la decisión ya evaluada por el llamador")
            return custom_decision

        raise LeadQualificationFailedError(f"Modelo de calificación desconocido: {model!r}")
