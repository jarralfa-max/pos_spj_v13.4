"""FeatureFlagRule — SET-21 "Rules"/"Rollout": one targeting override for
a `FeatureFlag` at a given scope. Generalizes the legacy repository's
`branch_id IN (?, 0) ORDER BY branch_id DESC` precedence (branch-specific
beats global) into an explicit `FeatureFlagScopeType` ranking, and adds
`rollout_percentage` — a gradual-rollout dimension the legacy bool-only
schema never had at all (§21 "Rollout").

`rollout_percentage` only matters when `enabled=True`: 100 means fully on
for this scope, less than 100 means a deterministic subset (see
`policies/feature_flag_evaluation_policy.py::_in_rollout`) sees it
enabled. A disabled rule (`enabled=False`) always evaluates to off
regardless of `rollout_percentage`.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

from backend.domain.feature_flags.enums import FeatureFlagScopeType
from backend.domain.feature_flags.exceptions import FeatureFlagsInvalidValueError
from backend.shared.ids import new_uuid, validate_uuidv7


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass(slots=True)
class FeatureFlagRule:
    id: str
    flag_id: str
    scope_type: FeatureFlagScopeType
    scope_id: str | None
    enabled: bool
    rollout_percentage: int = 100
    active: bool = True
    created_at: str = field(default_factory=_utcnow)
    updated_at: str = field(default_factory=_utcnow)

    @classmethod
    def create(
        cls, *, flag_id: str, scope_type: FeatureFlagScopeType, scope_id: str | None, enabled: bool,
        rollout_percentage: int = 100,
    ) -> "FeatureFlagRule":
        if scope_type is FeatureFlagScopeType.GLOBAL and scope_id is not None:
            raise FeatureFlagsInvalidValueError("scope_type=GLOBAL no debe llevar scope_id")
        if scope_type is not FeatureFlagScopeType.GLOBAL and not scope_id:
            raise FeatureFlagsInvalidValueError(f"scope_type={scope_type.value} requiere scope_id")
        if (
            isinstance(rollout_percentage, bool) or not isinstance(rollout_percentage, int)
            or not (0 <= rollout_percentage <= 100)
        ):
            raise FeatureFlagsInvalidValueError(
                f"rollout_percentage debe ser un entero entre 0 y 100, recibido {rollout_percentage!r}"
            )
        return cls(
            id=new_uuid(), flag_id=validate_uuidv7(flag_id), scope_type=scope_type, scope_id=scope_id,
            enabled=bool(enabled), rollout_percentage=rollout_percentage,
        )

    def _touch(self) -> None:
        self.updated_at = _utcnow()

    def activate(self) -> None:
        self.active = True
        self._touch()

    def deactivate(self) -> None:
        self.active = False
        self._touch()

    def matches(self, scope_type: FeatureFlagScopeType, scope_id: str | None) -> bool:
        return self.active and self.scope_type is scope_type and self.scope_id == scope_id
