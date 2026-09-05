"""AssetCategory — configurable asset classification catalog (§15).

Categories are seed-configurable data, never hardcoded in the UI or in
domain/application code (master prompt §15).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

from backend.domain.assets.enums import AssetCategoryStatus
from backend.domain.assets.exceptions import AssetDomainError
from backend.shared.ids import new_uuid


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass(slots=True)
class AssetCategory:
    id: str
    name: str
    code: str
    parent_category_id: str | None = None
    status: AssetCategoryStatus = AssetCategoryStatus.ACTIVE
    notes: str = ""
    created_at: str = field(default_factory=_utcnow)
    updated_at: str = field(default_factory=_utcnow)

    @classmethod
    def create(cls, name: str, code: str, *, parent_category_id: str | None = None,
               notes: str = "") -> "AssetCategory":
        if not name or not name.strip():
            raise AssetDomainError("AssetCategory.name is required")
        if not code or not code.strip():
            raise AssetDomainError("AssetCategory.code is required")
        return cls(
            id=new_uuid(),
            name=name.strip(),
            code=code.strip().upper(),
            parent_category_id=parent_category_id,
            notes=notes,
        )

    def rename(self, name: str) -> None:
        if not name or not name.strip():
            raise AssetDomainError("AssetCategory.name is required")
        self.name = name.strip()
        self.updated_at = _utcnow()

    def deactivate(self) -> None:
        self.status = AssetCategoryStatus.INACTIVE
        self.updated_at = _utcnow()

    def reactivate(self) -> None:
        self.status = AssetCategoryStatus.ACTIVE
        self.updated_at = _utcnow()

    def is_active(self) -> bool:
        return self.status is AssetCategoryStatus.ACTIVE
