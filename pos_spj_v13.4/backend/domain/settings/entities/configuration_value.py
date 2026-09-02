"""ConfigurationValue — one versioned, scoped, effective-dated assignment
of a `ConfigurationDefinition` (§10-11).

Status machine::

    DRAFT ──submit_for_approval()──► PENDING_APPROVAL ──approve()──► APPROVED
      │                                    │                            │
      └──cancel()──► CANCELLED ◄───────────┴──reject(reason)──► REJECTED
                            ▲                                           │
                            └───────────────cancel()───────────────────┘
                                                                         │
                                                        activate(at) ────┤
                                                                         ▼
                                        SCHEDULED ──activate(at)──► ACTIVE
                                            │                          │
                                            └──cancel()──► CANCELLED   ├──expire(at)──► EXPIRED
                                                                       └──mark_rolled_back()──► ROLLED_BACK
                                                        EXPIRED ──mark_rolled_back()──► ROLLED_BACK

`activate()` lands on ACTIVE when `effective_period` already contains
`at`, or SCHEDULED when it starts in the future — calling `activate()`
again once that future date arrives moves SCHEDULED → ACTIVE. No method
ever mutates an ACTIVE value's `value` in place (§10: "No modificar
silenciosamente un valor activo. Crear una nueva versión.") — a change is
always a new `ConfigurationValue` row via `create_next_version()`.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

from backend.domain.settings.enums import ConfigurationValueStatus
from backend.domain.settings.exceptions import (
    ConfigurationActivationNotAllowedError,
    ConfigurationInvalidValueError,
    ConfigurationRollbackNotAllowedError,
)
from backend.domain.settings.value_objects.configuration_scope import ConfigurationScope
from backend.domain.settings.value_objects.effective_period import EffectivePeriod
from backend.domain.settings.value_objects.version_number import VersionNumber
from backend.shared.ids import new_uuid

_CANCELLABLE = {
    ConfigurationValueStatus.DRAFT, ConfigurationValueStatus.PENDING_APPROVAL,
    ConfigurationValueStatus.APPROVED, ConfigurationValueStatus.SCHEDULED,
}
_ROLLBACKABLE = {ConfigurationValueStatus.ACTIVE, ConfigurationValueStatus.EXPIRED}
_ACTIVATABLE = {ConfigurationValueStatus.APPROVED, ConfigurationValueStatus.SCHEDULED}


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _utcnow_iso() -> str:
    return _utcnow().isoformat(timespec="seconds")


@dataclass(slots=True)
class ConfigurationValue:
    id: str
    definition_id: str
    scope: ConfigurationScope
    value: object
    effective_period: EffectivePeriod
    version: VersionNumber
    status: ConfigurationValueStatus = ConfigurationValueStatus.DRAFT
    created_by_user_id: str | None = None
    approved_by_user_id: str | None = None
    activated_by_user_id: str | None = None
    reason: str | None = None
    previous_version_id: str | None = None
    created_at: str = field(default_factory=_utcnow_iso)
    updated_at: str = field(default_factory=_utcnow_iso)

    # construction ------------------------------------------------------------
    @classmethod
    def create(
        cls, *, definition_id: str, scope: ConfigurationScope, value: object,
        effective_period: EffectivePeriod, created_by_user_id: str | None = None,
        reason: str | None = None,
    ) -> "ConfigurationValue":
        if not definition_id:
            raise ConfigurationInvalidValueError("definition_id es obligatorio")
        return cls(
            id=new_uuid(), definition_id=definition_id, scope=scope, value=value,
            effective_period=effective_period, version=VersionNumber.first(),
            created_by_user_id=created_by_user_id, reason=reason,
        )

    def create_next_version(
        self, *, value: object, effective_period: EffectivePeriod,
        created_by_user_id: str | None = None, reason: str | None = None,
    ) -> "ConfigurationValue":
        """A configuration change is never an in-place edit — it is always a
        new DRAFT version chained to this one via `previous_version_id`."""
        return ConfigurationValue(
            id=new_uuid(), definition_id=self.definition_id, scope=self.scope, value=value,
            effective_period=effective_period, version=self.version.next(),
            created_by_user_id=created_by_user_id, reason=reason,
            previous_version_id=self.id,
        )

    def _touch(self) -> None:
        self.updated_at = _utcnow_iso()

    # lifecycle ---------------------------------------------------------------
    def submit_for_approval(self) -> None:
        if self.status is not ConfigurationValueStatus.DRAFT:
            raise ConfigurationActivationNotAllowedError(
                f"No se puede enviar a aprobación desde {self.status.value}"
            )
        self.status = ConfigurationValueStatus.PENDING_APPROVAL
        self._touch()

    def approve(self, approved_by_user_id: str) -> None:
        if self.status is not ConfigurationValueStatus.PENDING_APPROVAL:
            raise ConfigurationActivationNotAllowedError(
                f"No se puede aprobar desde {self.status.value}"
            )
        if not approved_by_user_id:
            raise ConfigurationInvalidValueError("approve() requiere approved_by_user_id")
        self.status = ConfigurationValueStatus.APPROVED
        self.approved_by_user_id = approved_by_user_id
        self._touch()

    def auto_approve(self, approved_by_user_id: str) -> None:
        """Skip PENDING_APPROVAL for definitions where
        `ConfigurationDefinition.approval_required` is False — the caller
        (an application-layer policy check) decides whether this is legal,
        not this entity."""
        if self.status is not ConfigurationValueStatus.DRAFT:
            raise ConfigurationActivationNotAllowedError(
                f"No se puede auto-aprobar desde {self.status.value}"
            )
        if not approved_by_user_id:
            raise ConfigurationInvalidValueError("auto_approve() requiere approved_by_user_id")
        self.status = ConfigurationValueStatus.APPROVED
        self.approved_by_user_id = approved_by_user_id
        self._touch()

    def reject(self, reason: str) -> None:
        if self.status is not ConfigurationValueStatus.PENDING_APPROVAL:
            raise ConfigurationActivationNotAllowedError(
                f"No se puede rechazar desde {self.status.value}"
            )
        if not reason.strip():
            raise ConfigurationInvalidValueError("reject() requiere un motivo")
        self.status = ConfigurationValueStatus.REJECTED
        self.reason = reason.strip()
        self._touch()

    def cancel(self) -> None:
        if self.status not in _CANCELLABLE:
            raise ConfigurationActivationNotAllowedError(
                f"No se puede cancelar desde {self.status.value}"
            )
        self.status = ConfigurationValueStatus.CANCELLED
        self._touch()

    def activate(self, activated_by_user_id: str, *, at: datetime | None = None) -> None:
        if self.status not in _ACTIVATABLE:
            raise ConfigurationActivationNotAllowedError(
                f"No se puede activar desde {self.status.value}"
            )
        if not activated_by_user_id:
            raise ConfigurationInvalidValueError("activate() requiere activated_by_user_id")
        moment = at or _utcnow()
        if self.effective_period.is_future(moment):
            self.status = ConfigurationValueStatus.SCHEDULED
        else:
            self.status = ConfigurationValueStatus.ACTIVE
        self.activated_by_user_id = activated_by_user_id
        self._touch()

    def expire(self, *, at: datetime | None = None) -> None:
        if self.status is not ConfigurationValueStatus.ACTIVE:
            raise ConfigurationActivationNotAllowedError(
                f"No se puede expirar desde {self.status.value}"
            )
        moment = at or _utcnow()
        if not self.effective_period.has_expired(moment):
            raise ConfigurationActivationNotAllowedError(
                "effective_to aún no se alcanza — no se puede expirar todavía"
            )
        self.status = ConfigurationValueStatus.EXPIRED
        self._touch()

    def mark_rolled_back(self) -> None:
        if self.status not in _ROLLBACKABLE:
            raise ConfigurationRollbackNotAllowedError(
                f"No se puede hacer rollback desde {self.status.value}"
            )
        self.status = ConfigurationValueStatus.ROLLED_BACK
        self._touch()

    # queries -------------------------------------------------------------------
    def is_effective(self, at: datetime | None = None) -> bool:
        return self.status is ConfigurationValueStatus.ACTIVE and self.effective_period.contains(
            at or _utcnow()
        )
