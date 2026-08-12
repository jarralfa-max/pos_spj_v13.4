"""CRMStageTransitionPolicy — validates a proposed opportunity stage move
without hardcoding the pipeline shape (§19-22: "cada transición valida
permiso, campos obligatorios, actividad mínima, motivo, probabilidad, fecha
esperada"). Permission itself is NOT checked here (that stays an
application-layer concern via ``CRMAuthorizationPolicy``, same split as
every other CRM use case) — this policy owns the remaining four checks:
required fields, minimum logged activity, a reason for backward moves, and
probability/target-stage sanity.

Pure domain logic — no I/O, never touches a repository. Callers pass in
already-loaded ``CRMStageDefinition`` rows and an activity count (CRM-6
doesn't exist yet, so callers currently pass 0 — see
``MoveOpportunityStageUseCase`` for the documented stub).
"""

from __future__ import annotations

from datetime import date

from backend.domain.crm.entities.opportunity import Opportunity
from backend.domain.crm.entities.stage_definition import CRMStageDefinition
from backend.domain.crm.enums import OpportunityStatus
from backend.domain.crm.exceptions import OpportunityStageTransitionNotAllowedError

_MOVABLE_STATUSES = {OpportunityStatus.OPEN, OpportunityStatus.ON_HOLD}


def _field_present(opportunity: Opportunity, field_name: str, *,
                    probability: int | None, expected_close_date: date | None) -> bool:
    if field_name == "amount":
        return opportunity.amount is not None
    if field_name == "expected_close_date":
        return (expected_close_date if expected_close_date is not None
                else opportunity.expected_close_date) is not None
    if field_name == "probability":
        return (probability if probability is not None else opportunity.probability) is not None
    return bool(getattr(opportunity, field_name, None))


class CRMStageTransitionPolicy:
    def validate(
        self, opportunity: Opportunity, from_stage: CRMStageDefinition | None,
        to_stage: CRMStageDefinition, *, reason: str = "", probability: int | None = None,
        expected_close_date: date | None = None, activities_logged_count: int = 0,
        override: bool = False,
    ) -> None:
        if opportunity.status not in _MOVABLE_STATUSES:
            raise OpportunityStageTransitionNotAllowedError(
                f"No se puede cambiar de etapa desde {opportunity.status.value}")
        if not to_stage.active:
            raise OpportunityStageTransitionNotAllowedError(
                f"La etapa {to_stage.code} no está activa")
        if probability is not None and not (0 <= probability <= 100):
            raise OpportunityStageTransitionNotAllowedError(
                "probability debe estar entre 0 y 100")

        if override:
            # OPPORTUNITIES_OVERRIDE_STAGE bypasses required-field/minimum-
            # activity/backward-move checks, but never the audit trail — a
            # reason is still mandatory so the override is accountable.
            if not reason.strip():
                raise OpportunityStageTransitionNotAllowedError(
                    "Sobrescribir etapa requiere un motivo")
            return

        if (from_stage is not None and to_stage.sequence_order < from_stage.sequence_order
                and not reason.strip()):
            raise OpportunityStageTransitionNotAllowedError(
                "Retroceder de etapa requiere un motivo")

        if activities_logged_count < to_stage.min_activities:
            raise OpportunityStageTransitionNotAllowedError(
                f"La etapa {to_stage.name} requiere al menos "
                f"{to_stage.min_activities} actividad(es) registradas "
                f"({activities_logged_count} registrada(s))")

        missing = [
            field_name for field_name in to_stage.required_fields
            if not _field_present(opportunity, field_name, probability=probability,
                                  expected_close_date=expected_close_date)
        ]
        if missing:
            raise OpportunityStageTransitionNotAllowedError(
                f"La etapa {to_stage.name} requiere: {', '.join(missing)}")
