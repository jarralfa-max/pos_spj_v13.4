"""LoyaltyCardTemplate — the business-level approval gate for a card design
family (master prompt §33). Governs whether the template is available for
issuance/batches AT ALL; which specific design snapshot is currently live
is `LoyaltyCardTemplateVersion`'s own, separate concern (§33's own split
between "aprobar plantilla" and "activar plantilla" as distinct permission
actions — see `LoyaltyCardsPermissions.TEMPLATE_APPROVE`/`TEMPLATE_ACTIVATE`,
already defined in LOY-1)."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

from backend.domain.loyalty_cards.enums import (
    LoyaltyCardTemplateStatus,
    LoyaltyCardTemplateTargetType,
)
from backend.domain.loyalty_cards.exceptions import (
    InvalidLoyaltyCardTemplateError,
    InvalidLoyaltyCardTemplateStateError,
)
from backend.shared.ids import new_uuid


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass(slots=True)
class LoyaltyCardTemplate:
    id: str
    code: str
    name: str
    description: str = ""
    target_type: LoyaltyCardTemplateTargetType = LoyaltyCardTemplateTargetType.PHYSICAL
    status: LoyaltyCardTemplateStatus = LoyaltyCardTemplateStatus.DRAFT
    active_version_id: str | None = None
    created_by_user_id: str = ""
    approved_by_user_id: str | None = None
    created_at: str = field(default_factory=_utcnow)
    updated_at: str = field(default_factory=_utcnow)

    def __post_init__(self) -> None:
        if not self.code or not self.code.strip():
            raise InvalidLoyaltyCardTemplateError("code es obligatorio")
        if not self.name or not self.name.strip():
            raise InvalidLoyaltyCardTemplateError("name es obligatorio")

    @classmethod
    def create(cls, code: str, name: str, *, created_by_user_id: str,
               **kwargs) -> "LoyaltyCardTemplate":
        return cls(id=new_uuid(), code=code.strip(), name=name.strip(),
                    created_by_user_id=created_by_user_id, **kwargs)

    def submit_for_approval(self) -> None:
        if self.status is not LoyaltyCardTemplateStatus.DRAFT:
            raise InvalidLoyaltyCardTemplateStateError(
                f"Solo se envía a aprobación desde DRAFT (actual: {self.status.value})")
        self.status = LoyaltyCardTemplateStatus.PENDING_APPROVAL
        self.updated_at = _utcnow()

    def approve(self, approved_by_user_id: str) -> None:
        if self.status is not LoyaltyCardTemplateStatus.PENDING_APPROVAL:
            raise InvalidLoyaltyCardTemplateStateError(
                f"Solo se aprueba desde PENDING_APPROVAL (actual: {self.status.value})")
        if approved_by_user_id == self.created_by_user_id:
            raise InvalidLoyaltyCardTemplateStateError(
                "Quien aprueba no puede ser quien creó la plantilla (segregación de funciones)")
        self.status = LoyaltyCardTemplateStatus.APPROVED
        self.approved_by_user_id = approved_by_user_id
        self.updated_at = _utcnow()

    def activate(self, active_version_id: str) -> None:
        """§33: a template may only go ACTIVE once it has at least one
        APPROVED version — that cross-row check lives in the application
        layer (a repository lookup), not here; this method only enforces
        the template's OWN state transition and records which version is
        now live."""
        if self.status not in (LoyaltyCardTemplateStatus.APPROVED, LoyaltyCardTemplateStatus.ACTIVE):
            raise InvalidLoyaltyCardTemplateStateError(
                f"Solo se activa desde APPROVED/ACTIVE (actual: {self.status.value})")
        self.status = LoyaltyCardTemplateStatus.ACTIVE
        self.active_version_id = active_version_id
        self.updated_at = _utcnow()

    def archive(self) -> None:
        if self.status is LoyaltyCardTemplateStatus.ARCHIVED:
            raise InvalidLoyaltyCardTemplateStateError("La plantilla ya está archivada")
        self.status = LoyaltyCardTemplateStatus.ARCHIVED
        self.updated_at = _utcnow()

    def is_available_for_issuance(self) -> bool:
        return self.status is LoyaltyCardTemplateStatus.ACTIVE and self.active_version_id is not None
