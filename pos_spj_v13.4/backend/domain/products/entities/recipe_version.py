"""RecipeVersion — an immutable, versioned recipe revision (§22).

Every recipe change is a new version: DRAFT → UNDER_REVIEW → APPROVED → ACTIVE →
SUPERSEDED/INACTIVE. An APPROVED/ACTIVE version is immutable — you don't edit it,
you create a new version. Components/outputs may only change while the version is
still DRAFT/UNDER_REVIEW.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

from backend.domain.products.entities.recipe_component import RecipeComponent
from backend.domain.products.entities.recipe_output import RecipeOutput
from backend.domain.products.exceptions import (
    InvalidRecipeError,
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
class RecipeVersion:
    recipe_id: str
    version_number: int
    id: str = field(default_factory=new_uuid)
    status: RecipeVersionStatus = RecipeVersionStatus.DRAFT
    components: list[RecipeComponent] = field(default_factory=list)
    outputs: list[RecipeOutput] = field(default_factory=list)
    effective_from: str | None = None
    effective_to: str | None = None
    approved_by_user_id: str | None = None
    reason: str | None = None

    def __post_init__(self) -> None:
        if not self.recipe_id:
            raise InvalidRecipeError("La versión requiere receta")
        if int(self.version_number) < 1:
            raise InvalidRecipeError("version_number debe ser >= 1")
        if not isinstance(self.status, RecipeVersionStatus):
            self.status = RecipeVersionStatus(str(self.status))

    @property
    def is_editable(self) -> bool:
        return self.status not in IMMUTABLE_VERSION_STATES

    def _guard_editable(self) -> None:
        if not self.is_editable:
            raise RecipeVersionImmutableError(
                f"La versión {self.version_number} está {self.status.value} y es inmutable (§22)")

    def add_component(self, component: RecipeComponent) -> None:
        self._guard_editable()
        component.version_id = self.id
        self.components.append(component)

    def add_output(self, output: RecipeOutput) -> None:
        self._guard_editable()
        output.version_id = self.id
        self.outputs.append(output)

    def component_product_ids(self) -> list[str]:
        return [c.component_product_id for c in self.components]

    # ── transiciones (§22) ────────────────────────────────────────────────
    def _transition(self, target: RecipeVersionStatus) -> None:
        if target not in _TRANSITIONS.get(self.status, frozenset()):
            raise InvalidRecipeError(
                f"Transición de versión no permitida: {self.status.value} → {target.value}")
        self.status = target

    def submit(self) -> None:
        if not self.components and not self.outputs:
            raise InvalidRecipeError("Una versión no puede enviarse sin componentes ni outputs")
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
