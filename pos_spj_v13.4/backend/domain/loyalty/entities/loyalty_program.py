"""LoyaltyProgram — the configuration root for a Fidelidad program (§9).

No hardcoded currency name, multipliers, bonuses, tiers, validities, minimums
or maximums (§9) — everything a program needs lives in its own fields or in
``LoyaltyRule``/``LoyaltyTier`` (later phases), never as a literal in code.

Approval and activation are deliberately two separate steps (§59/§60:
``programa.aprobar`` and ``programa.activar`` are distinct permissions) so a
program can be reviewed by one user and switched on by another — mirrors
``backend/domain/customers/entities/customer.py``'s lifecycle-method shape.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

from backend.domain.loyalty.enums import ProgramStatus
from backend.domain.loyalty.exceptions import InvalidLoyaltyProgramStateError
from backend.shared.ids import new_uuid


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass(slots=True)
class LoyaltyProgram:
    id: str
    code: str
    name: str
    currency_name: str
    description: str = ""
    currency_symbol: str = ""
    status: ProgramStatus = ProgramStatus.DRAFT
    enrollment_mode: str = "OPEN"
    earning_enabled: bool = True
    redemption_enabled: bool = True
    tiering_enabled: bool = False
    expiration_enabled: bool = False
    branch_scope: str | None = None
    channel_scope: str | None = None
    effective_from: str | None = None
    effective_to: str | None = None
    created_by_user_id: str | None = None
    approved_by_user_id: str | None = None
    approved_at: str | None = None
    activated_at: str | None = None
    suspended_at: str | None = None
    closed_at: str | None = None
    created_at: str = field(default_factory=_utcnow)
    updated_at: str = field(default_factory=_utcnow)

    @classmethod
    def create(
        cls, code: str, name: str, currency_name: str, *,
        description: str = "", currency_symbol: str = "",
        created_by_user_id: str | None = None,
    ) -> "LoyaltyProgram":
        if not code or not code.strip():
            raise InvalidLoyaltyProgramStateError("code es obligatorio")
        if not name or not name.strip():
            raise InvalidLoyaltyProgramStateError("name es obligatorio")
        if not currency_name or not currency_name.strip():
            raise InvalidLoyaltyProgramStateError("currency_name es obligatorio")
        return cls(
            id=new_uuid(), code=code.strip(), name=name.strip(),
            currency_name=currency_name.strip(), description=description,
            currency_symbol=currency_symbol, created_by_user_id=created_by_user_id,
        )

    def _touch(self) -> None:
        self.updated_at = _utcnow()

    def submit_for_approval(self) -> None:
        if self.status is not ProgramStatus.DRAFT:
            raise InvalidLoyaltyProgramStateError(
                f"No se puede enviar a aprobación desde {self.status.value}")
        self.status = ProgramStatus.PENDING_APPROVAL
        self._touch()

    def approve(self, approved_by_user_id: str) -> None:
        if self.status is not ProgramStatus.PENDING_APPROVAL:
            raise InvalidLoyaltyProgramStateError(
                f"No se puede aprobar desde {self.status.value}")
        if not approved_by_user_id:
            raise InvalidLoyaltyProgramStateError("La aprobación requiere approved_by_user_id")
        self.approved_by_user_id = approved_by_user_id
        self.approved_at = _utcnow()
        self._touch()

    def activate(self) -> None:
        if self.status is ProgramStatus.SUSPENDED:
            self.status = ProgramStatus.ACTIVE
            self.activated_at = _utcnow()
            self._touch()
            return
        if self.status is not ProgramStatus.PENDING_APPROVAL:
            raise InvalidLoyaltyProgramStateError(
                f"No se puede activar desde {self.status.value}")
        if not self.approved_by_user_id:
            raise InvalidLoyaltyProgramStateError(
                "El programa debe aprobarse antes de activarse")
        self.status = ProgramStatus.ACTIVE
        self.activated_at = _utcnow()
        self._touch()

    def suspend(self, reason: str) -> None:
        if self.status is not ProgramStatus.ACTIVE:
            raise InvalidLoyaltyProgramStateError(
                f"Solo se suspende un programa activo (actual: {self.status.value})")
        if not (reason or "").strip():
            raise InvalidLoyaltyProgramStateError("La suspensión requiere un motivo")
        self.status = ProgramStatus.SUSPENDED
        self.suspended_at = _utcnow()
        self._touch()

    def close(self, reason: str) -> None:
        if self.status not in (ProgramStatus.ACTIVE, ProgramStatus.SUSPENDED):
            raise InvalidLoyaltyProgramStateError(
                f"No se puede cerrar desde {self.status.value}")
        if not (reason or "").strip():
            raise InvalidLoyaltyProgramStateError("El cierre requiere un motivo")
        self.status = ProgramStatus.CLOSED
        self.closed_at = _utcnow()
        self._touch()

    def archive(self) -> None:
        if self.status is not ProgramStatus.CLOSED:
            raise InvalidLoyaltyProgramStateError(
                f"Solo se archiva un programa cerrado (actual: {self.status.value})")
        self.status = ProgramStatus.ARCHIVED
        self._touch()

    def is_active(self) -> bool:
        return self.status is ProgramStatus.ACTIVE
