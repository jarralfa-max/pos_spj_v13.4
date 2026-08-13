"""CustomerPortfolio — the configurable "cartera de clientes" catalog
(§33-36). A book of accounts a sales rep/team manages; which customers
belong to it is tracked separately by PortfolioAssignment (append-only
history), not by a column here.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

from backend.domain.crm.exceptions import InvalidCustomerPortfolioError
from backend.shared.ids import new_uuid


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass(slots=True)
class CustomerPortfolio:
    id: str
    code: str
    name: str
    description: str = ""
    manager_user_id: str | None = None
    active: bool = True
    created_at: str = field(default_factory=_utcnow)
    updated_at: str = field(default_factory=_utcnow)

    @classmethod
    def create(cls, code: str, name: str, *, description: str = "",
               manager_user_id: str | None = None) -> "CustomerPortfolio":
        if not code or not code.strip():
            raise InvalidCustomerPortfolioError("code es obligatorio")
        if not name or not name.strip():
            raise InvalidCustomerPortfolioError("name es obligatorio")
        return cls(id=new_uuid(), code=code.strip().upper(), name=name.strip(),
                    description=description.strip(), manager_user_id=manager_user_id)

    def deactivate(self) -> None:
        self.active = False
        self.updated_at = _utcnow()
