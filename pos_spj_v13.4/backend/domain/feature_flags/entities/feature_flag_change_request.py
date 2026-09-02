"""FeatureFlagChangeRequest — SET-21 "Approval": a proposed
`FeatureFlagRule` change that must be approved by a *different* user
before it takes effect. The legacy `FeatureFlagService.set_flag()` writes
directly, no review step — for a switch that can silently disable a
whole ERP module for a branch (or roll it out to real customers), that
gap is exactly what this entity closes.

Status machine::

    PENDING_APPROVAL ──approve()──► APPROVED ──apply()──► APPLIED (terminal)
           │
           └──────reject(reason)──► REJECTED (terminal)

Only 4 states — simpler than `DocumentTemplateVersion`'s 7 (SET-11):
there is no draft-editing phase here, a change request is proposed
already-formed, and once decided (approved/applied or rejected) it is
never revised in place — a corrected proposal is a new request.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

from backend.domain.feature_flags.entities.feature_flag_rule import FeatureFlagRule
from backend.domain.feature_flags.enums import FeatureFlagChangeStatus, FeatureFlagScopeType
from backend.domain.feature_flags.exceptions import (
    FeatureFlagChangeTransitionNotAllowedError,
    FeatureFlagsInvalidValueError,
)
from backend.shared.ids import new_uuid, validate_uuidv7

_APPROVABLE = {FeatureFlagChangeStatus.PENDING_APPROVAL}
_REJECTABLE = {FeatureFlagChangeStatus.PENDING_APPROVAL}
_APPLICABLE = {FeatureFlagChangeStatus.APPROVED}


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass(slots=True)
class FeatureFlagChangeRequest:
    id: str
    flag_id: str
    scope_type: FeatureFlagScopeType
    scope_id: str | None
    proposed_enabled: bool
    proposed_rollout_percentage: int
    requested_by_user_id: str
    status: FeatureFlagChangeStatus = FeatureFlagChangeStatus.PENDING_APPROVAL
    approved_by_user_id: str | None = None
    reason: str | None = None
    created_at: str = field(default_factory=_utcnow)
    updated_at: str = field(default_factory=_utcnow)

    @classmethod
    def create(
        cls, *, flag_id: str, scope_type: FeatureFlagScopeType, scope_id: str | None,
        proposed_enabled: bool, requested_by_user_id: str, proposed_rollout_percentage: int = 100,
    ) -> "FeatureFlagChangeRequest":
        if not requested_by_user_id:
            raise FeatureFlagsInvalidValueError("requested_by_user_id es obligatorio")
        if (
            isinstance(proposed_rollout_percentage, bool) or not isinstance(proposed_rollout_percentage, int)
            or not (0 <= proposed_rollout_percentage <= 100)
        ):
            raise FeatureFlagsInvalidValueError(
                f"proposed_rollout_percentage debe ser un entero entre 0 y 100, "
                f"recibido {proposed_rollout_percentage!r}"
            )
        return cls(
            id=new_uuid(), flag_id=validate_uuidv7(flag_id), scope_type=scope_type, scope_id=scope_id,
            proposed_enabled=bool(proposed_enabled), proposed_rollout_percentage=proposed_rollout_percentage,
            requested_by_user_id=requested_by_user_id,
        )

    def _touch(self) -> None:
        self.updated_at = _utcnow()

    def approve(self, approved_by_user_id: str) -> None:
        if self.status not in _APPROVABLE:
            raise FeatureFlagChangeTransitionNotAllowedError(
                f"No se puede aprobar desde {self.status.value}"
            )
        if not approved_by_user_id:
            raise FeatureFlagsInvalidValueError("approve() requiere approved_by_user_id")
        self.status = FeatureFlagChangeStatus.APPROVED
        self.approved_by_user_id = approved_by_user_id
        self._touch()

    def reject(self, reason: str) -> None:
        if self.status not in _REJECTABLE:
            raise FeatureFlagChangeTransitionNotAllowedError(
                f"No se puede rechazar desde {self.status.value}"
            )
        if not reason.strip():
            raise FeatureFlagsInvalidValueError("reject() requiere un motivo")
        self.status = FeatureFlagChangeStatus.REJECTED
        self.reason = reason.strip()
        self._touch()

    def apply(self) -> FeatureFlagRule:
        if self.status not in _APPLICABLE:
            raise FeatureFlagChangeTransitionNotAllowedError(
                f"No se puede aplicar desde {self.status.value}"
            )
        rule = FeatureFlagRule.create(
            flag_id=self.flag_id, scope_type=self.scope_type, scope_id=self.scope_id,
            enabled=self.proposed_enabled, rollout_percentage=self.proposed_rollout_percentage,
        )
        self.status = FeatureFlagChangeStatus.APPLIED
        self._touch()
        return rule
