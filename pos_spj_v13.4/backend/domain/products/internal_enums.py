"""Internal / work-in-progress product enums (§13).

PROD-6. An internal product is one that lives in inventory, may be an input or
output of a recipe, may be costed and quality/lot-controlled, but is NOT offered
in POS/e-commerce. The stage classifies *where in the flow* it sits. Turning one
stage into another that is a real transformation is a distinct product plus an
explicit technical relationship — never a duplicate identity (§5).
"""

from __future__ import annotations

from enum import Enum


class InternalStage(str, Enum):
    NONE = "NONE"                       # not an internal product
    INTERNAL_ONLY = "INTERNAL_ONLY"     # internal, not a WIP stage per se
    WORK_IN_PROGRESS = "WORK_IN_PROGRESS"
    SEMI_FINISHED = "SEMI_FINISHED"
    PROCESS_INTERMEDIATE = "PROCESS_INTERMEDIATE"


# Etapas que representan producto interno no vendible (§13).
INTERNAL_STAGES = frozenset({
    InternalStage.INTERNAL_ONLY,
    InternalStage.WORK_IN_PROGRESS,
    InternalStage.SEMI_FINISHED,
    InternalStage.PROCESS_INTERMEDIATE,
})
