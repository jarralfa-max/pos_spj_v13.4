"""CuttingSchemeVersion — a versioned disassembly plan (§22, §24).

Same versioning lifecycle and immutability as recipes/yields. Holds the ordered
list of cutting outputs (cuts, offal, waste) produced from the scheme's input.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

from backend.domain.products.entities.cutting_output import CuttingOutput
from backend.domain.products.exceptions import (
    CuttingSchemeInvalidError,
    RecipeVersionImmutableError,
)
from backend.domain.products.recipe_enums import (
    IMMUTABLE_VERSION_STATES,
    RecipeVersionStatus,
)
from backend.shared.ids import new_uuid

_TRANSITIONS = {
    RecipeVersionStatus.DRAFT: frozenset(
        {RecipeVersionStatus.UNDER_REVIEW, RecipeVersionStatus.INACTIVE}),
    RecipeVersionStatus.UNDER_REVIEW: frozenset(
        {RecipeVersionStatus.DRAFT, RecipeVersionStatus.APPROVED, RecipeVersionStatus.INACTIVE}),
    RecipeVersionStatus.APPROVED: frozenset(
        {RecipeVersionStatus.ACTIVE, RecipeVersionStatus.INACTIVE}),
    RecipeVersionStatus.ACTIVE: frozenset(
        {RecipeVersionStatus.SUPERSEDED, RecipeVersionStatus.INACTIVE}),
    RecipeVersionStatus.SUPERSEDED: frozenset({RecipeVersionStatus.INACTIVE}),
    RecipeVersionStatus.INACTIVE: frozenset(),
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass
class CuttingSchemeVersion:
    cutting_scheme_id: str
    version_number: int
    id: str = field(default_factory=new_uuid)
    status: RecipeVersionStatus = RecipeVersionStatus.DRAFT
    outputs: list[CuttingOutput] = field(default_factory=list)
    effective_from: str | None = None
    effective_to: str | None = None
    approved_by_user_id: str | None = None
    reason: str | None = None

    def __post_init__(self) -> None:
        if not self.cutting_scheme_id:
            raise CuttingSchemeInvalidError("La versión requiere esquema de despiece")
        if int(self.version_number) < 1:
            raise CuttingSchemeInvalidError("version_number debe ser >= 1")
        if not isinstance(self.status, RecipeVersionStatus):
            self.status = RecipeVersionStatus(str(self.status))

    @property
    def is_editable(self) -> bool:
        return self.status not in IMMUTABLE_VERSION_STATES

    def add_output(self, output: CuttingOutput) -> None:
        if not self.is_editable:
            raise RecipeVersionImmutableError(
                f"La versión {self.version_number} está {self.status.value} y es inmutable (§22)")
        output.version_id = self.id
        self.outputs.append(output)

    def output_product_ids(self) -> list[str]:
        return [o.product_id for o in self.outputs]

    def _transition(self, target: RecipeVersionStatus) -> None:
        if target not in _TRANSITIONS.get(self.status, frozenset()):
            raise CuttingSchemeInvalidError(
                f"Transición no permitida: {self.status.value} → {target.value}")
        self.status = target

    def submit(self) -> None:
        if not self.outputs:
            raise CuttingSchemeInvalidError("Una versión no puede enviarse sin outputs")
        self._transition(RecipeVersionStatus.UNDER_REVIEW)

    def approve(self, *, approved_by_user_id: str, reason: str | None = None) -> None:
        self._transition(RecipeVersionStatus.APPROVED)
        self.approved_by_user_id = approved_by_user_id
        self.reason = reason

    def activate(self) -> None:
        self._transition(RecipeVersionStatus.ACTIVE)
        self.effective_from = self.effective_from or _now()

    def supersede(self) -> None:
        self._transition(RecipeVersionStatus.SUPERSEDED)
        self.effective_to = _now()

    def deactivate(self) -> None:
        self._transition(RecipeVersionStatus.INACTIVE)
