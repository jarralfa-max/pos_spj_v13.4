"""CostCenter entity."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

from backend.domain.finance.exceptions import FinanceDomainError
from backend.shared.ids import new_uuid


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass(slots=True)
class CostCenter:
    id: str
    code: str
    name: str
    parent_id: str | None = None
    branch_id: str | None = None
    active: bool = True
    created_at: str = field(default_factory=_utcnow)

    @classmethod
    def create(cls, code: str, name: str, *, parent_id: str | None = None,
               branch_id: str | None = None) -> "CostCenter":
        if not code or not name:
            raise FinanceDomainError("CostCenter requires code and name")
        return cls(id=new_uuid(), code=code.strip(), name=name.strip(),
                   parent_id=parent_id, branch_id=branch_id)
