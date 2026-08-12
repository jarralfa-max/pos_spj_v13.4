"""CRMStageDefinition — the configurable pipeline stage catalog (§19-22,
"Pipeline configurable vía CRMStageDefinition/CRMStageTransitionPolicy
(nunca hardcodeado)"). A stage is data, never a hardcoded enum branch — this
is what lets an admin add/reorder/retire pipeline stages without a code
change. ``Opportunity.stage_id`` references a row here; the two terminal
flags (``is_won_stage``/``is_lost_stage``) let WinOpportunityUseCase/
LoseOpportunityUseCase resolve which stage to land on without guessing.

CRM-5 seeds a sensible default 6-stage pipeline via migration 183 (see
docs/refactor/CRM-5_oportunidades.md) so the system is usable out of the
box; a fully permissioned stage-configuration use case is deferred (no
``CRM.pipeline.configurar``-shaped permission exists in CRM-2's catalog —
inventing one here would be scope creep on a security decision that
belongs to a phase that actually builds the admin UI, CRM-14+).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

from backend.domain.crm.exceptions import InvalidStageDefinitionError
from backend.shared.ids import new_uuid


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass(slots=True)
class CRMStageDefinition:
    id: str
    code: str
    name: str
    sequence_order: int
    probability_default: int = 0
    is_won_stage: bool = False
    is_lost_stage: bool = False
    required_fields: tuple[str, ...] = field(default_factory=tuple)
    min_activities: int = 0
    active: bool = True
    created_at: str = field(default_factory=_utcnow)
    updated_at: str = field(default_factory=_utcnow)

    @classmethod
    def create(
        cls, code: str, name: str, sequence_order: int, *, probability_default: int = 0,
        is_won_stage: bool = False, is_lost_stage: bool = False,
        required_fields: tuple[str, ...] = (), min_activities: int = 0,
    ) -> "CRMStageDefinition":
        if not code or not code.strip():
            raise InvalidStageDefinitionError("code es obligatorio")
        if not name or not name.strip():
            raise InvalidStageDefinitionError("name es obligatorio")
        if is_won_stage and is_lost_stage:
            raise InvalidStageDefinitionError(
                "Una etapa no puede ser ganada y perdida a la vez")
        if not (0 <= probability_default <= 100):
            raise InvalidStageDefinitionError("probability_default debe estar entre 0 y 100")
        if min_activities < 0:
            raise InvalidStageDefinitionError("min_activities no puede ser negativo")
        return cls(
            id=new_uuid(), code=code.strip().upper(), name=name.strip(),
            sequence_order=sequence_order, probability_default=probability_default,
            is_won_stage=is_won_stage, is_lost_stage=is_lost_stage,
            required_fields=tuple(required_fields), min_activities=min_activities,
        )

    def deactivate(self) -> None:
        self.active = False
        self.updated_at = _utcnow()

    def is_terminal(self) -> bool:
        return self.is_won_stage or self.is_lost_stage
