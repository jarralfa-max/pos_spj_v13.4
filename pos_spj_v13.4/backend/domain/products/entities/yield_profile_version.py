"""YieldProfileVersion — a versioned expectation of a process' outputs (§22, §23).

Same lifecycle as recipes (DRAFT→UNDER_REVIEW→APPROVED→ACTIVE→SUPERSEDED/INACTIVE)
and the same immutability rule. Carries a configurable ``tolerance_pct`` used to
validate that the outputs sum near 100 % without hardcoding an exact 100 %.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation

from backend.domain.products.entities.yield_output import YieldOutput
from backend.domain.products.exceptions import (
    RecipeVersionImmutableError,
    YieldProfileInvalidError,
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


def _dec(value, label: str) -> Decimal:
    if isinstance(value, bool) or isinstance(value, float):
        raise YieldProfileInvalidError(f"{label} no puede ser float")
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise YieldProfileInvalidError(f"{label} inválido: {value!r}") from exc


@dataclass
class YieldProfileVersion:
    yield_profile_id: str
    version_number: int
    id: str = field(default_factory=new_uuid)
    status: RecipeVersionStatus = RecipeVersionStatus.DRAFT
    tolerance_pct: Decimal = Decimal("0")
    outputs: list[YieldOutput] = field(default_factory=list)
    effective_from: str | None = None
    effective_to: str | None = None
    approved_by_user_id: str | None = None
    reason: str | None = None

    def __post_init__(self) -> None:
        if not self.yield_profile_id:
            raise YieldProfileInvalidError("La versión requiere perfil de rendimiento")
        if int(self.version_number) < 1:
            raise YieldProfileInvalidError("version_number debe ser >= 1")
        if not isinstance(self.status, RecipeVersionStatus):
            self.status = RecipeVersionStatus(str(self.status))
        self.tolerance_pct = _dec(self.tolerance_pct, "tolerance_pct")
        if not (Decimal("0") <= self.tolerance_pct <= Decimal("100")):
            raise YieldProfileInvalidError("tolerance_pct debe estar en [0, 100]")

    @property
    def is_editable(self) -> bool:
        return self.status not in IMMUTABLE_VERSION_STATES

    def add_output(self, output: YieldOutput) -> None:
        if not self.is_editable:
            raise RecipeVersionImmutableError(
                f"La versión {self.version_number} está {self.status.value} y es inmutable (§22)")
        output.version_id = self.id
        self.outputs.append(output)

    def total_expected_yield(self) -> Decimal:
        return sum((o.expected_yield_pct for o in self.outputs), Decimal("0"))

    # ── transiciones ──────────────────────────────────────────────────────
    def _transition(self, target: RecipeVersionStatus) -> None:
        if target not in _TRANSITIONS.get(self.status, frozenset()):
            raise YieldProfileInvalidError(
                f"Transición no permitida: {self.status.value} → {target.value}")
        self.status = target

    def submit(self) -> None:
        if not self.outputs:
            raise YieldProfileInvalidError("Una versión no puede enviarse sin outputs")
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
