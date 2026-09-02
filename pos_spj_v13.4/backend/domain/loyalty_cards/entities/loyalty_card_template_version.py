"""LoyaltyCardTemplateVersion — one versioned design snapshot of a template
(master prompt §33-34). `design_schema_json` is a DECLARATIVE schema (JSON
describing layout/fields/QR placement) — never executable code.
`__post_init__` runs it through `validate_design_schema()` (LOY-18's own
closed allowlist: known element types/fields only, no HTML/script content,
no undeclared placeholder tokens) — a version can never be constructed,
saved, or rehydrated from the database with an invalid design.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

from backend.domain.loyalty_cards.design_schema import validate_design_schema
from backend.domain.loyalty_cards.enums import LoyaltyCardTemplateVersionStatus
from backend.domain.loyalty_cards.exceptions import (
    InvalidLoyaltyCardTemplateVersionError,
    InvalidLoyaltyCardTemplateVersionStateError,
)
from backend.shared.ids import new_uuid


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass(slots=True)
class LoyaltyCardTemplateVersion:
    id: str
    template_id: str
    version_number: int
    design_schema_json: str
    status: LoyaltyCardTemplateVersionStatus = LoyaltyCardTemplateVersionStatus.DRAFT
    created_by_user_id: str = ""
    approved_by_user_id: str | None = None
    activated_at: str | None = None
    created_at: str = field(default_factory=_utcnow)

    def __post_init__(self) -> None:
        if not self.template_id:
            raise InvalidLoyaltyCardTemplateVersionError("template_id es obligatorio")
        if self.version_number <= 0:
            raise InvalidLoyaltyCardTemplateVersionError("version_number debe ser positivo")
        validate_design_schema(self.design_schema_json)

    @classmethod
    def create(cls, template_id: str, version_number: int, design_schema_json: str, *,
               created_by_user_id: str) -> "LoyaltyCardTemplateVersion":
        return cls(id=new_uuid(), template_id=template_id, version_number=version_number,
                   design_schema_json=design_schema_json, created_by_user_id=created_by_user_id)

    def approve(self, approved_by_user_id: str) -> None:
        if self.status is not LoyaltyCardTemplateVersionStatus.DRAFT:
            raise InvalidLoyaltyCardTemplateVersionStateError(
                f"Solo se aprueba desde DRAFT (actual: {self.status.value})")
        if approved_by_user_id == self.created_by_user_id:
            raise InvalidLoyaltyCardTemplateVersionStateError(
                "Quien aprueba no puede ser quien creó la versión (segregación de funciones)")
        self.status = LoyaltyCardTemplateVersionStatus.APPROVED
        self.approved_by_user_id = approved_by_user_id

    def activate(self) -> None:
        if self.status is not LoyaltyCardTemplateVersionStatus.APPROVED:
            raise InvalidLoyaltyCardTemplateVersionStateError(
                f"Solo se activa desde APPROVED (actual: {self.status.value})")
        self.status = LoyaltyCardTemplateVersionStatus.ACTIVE
        self.activated_at = _utcnow()

    def archive(self) -> None:
        if self.status is LoyaltyCardTemplateVersionStatus.ARCHIVED:
            raise InvalidLoyaltyCardTemplateVersionStateError("La versión ya está archivada")
        self.status = LoyaltyCardTemplateVersionStatus.ARCHIVED
