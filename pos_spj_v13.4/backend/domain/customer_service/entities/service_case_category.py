"""ServiceCaseCategory — configurable case classification catalog (§30-32).
Data, not a hardcoded enum — mirrors
backend/domain/crm/entities/stage_definition.py::CRMStageDefinition.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

from backend.domain.customer_service.exceptions import InvalidServiceCaseCategoryError
from backend.shared.ids import new_uuid


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass(slots=True)
class ServiceCaseCategory:
    id: str
    code: str
    name: str
    active: bool = True
    created_at: str = field(default_factory=_utcnow)
    updated_at: str = field(default_factory=_utcnow)

    @classmethod
    def create(cls, code: str, name: str) -> "ServiceCaseCategory":
        if not code or not code.strip():
            raise InvalidServiceCaseCategoryError("code es obligatorio")
        if not name or not name.strip():
            raise InvalidServiceCaseCategoryError("name es obligatorio")
        return cls(id=new_uuid(), code=code.strip().upper(), name=name.strip())

    def deactivate(self) -> None:
        self.active = False
        self.updated_at = _utcnow()
