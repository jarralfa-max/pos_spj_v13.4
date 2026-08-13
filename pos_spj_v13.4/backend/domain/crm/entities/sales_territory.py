"""SalesTerritory — the configurable territory catalog (§33-36). A
territory is data, never a hardcoded enum branch — same trade-off
CRMStageDefinition already made for pipeline stages. ``Lead.territory_id``/
``Opportunity.territory_id``/``Customer.territory_id`` reference a row here
(loosely — those columns predate this catalog and were never FK-constrained,
so this migration does not retrofit a FK onto them).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

from backend.domain.crm.exceptions import InvalidSalesTerritoryError
from backend.shared.ids import new_uuid


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass(slots=True)
class SalesTerritory:
    id: str
    code: str
    name: str
    description: str = ""
    active: bool = True
    created_at: str = field(default_factory=_utcnow)
    updated_at: str = field(default_factory=_utcnow)

    @classmethod
    def create(cls, code: str, name: str, *, description: str = "") -> "SalesTerritory":
        if not code or not code.strip():
            raise InvalidSalesTerritoryError("code es obligatorio")
        if not name or not name.strip():
            raise InvalidSalesTerritoryError("name es obligatorio")
        return cls(id=new_uuid(), code=code.strip().upper(), name=name.strip(),
                    description=description.strip())

    def deactivate(self) -> None:
        self.active = False
        self.updated_at = _utcnow()
