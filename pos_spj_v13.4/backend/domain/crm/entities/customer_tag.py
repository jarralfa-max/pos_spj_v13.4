"""CustomerTag — the free-form label catalog (§33-36). "No sustituyen
estatus/segmento/riesgo/consentimiento/territorio" — tags are cosmetic
markers a user can attach for their own operational triage, never a
condition another bounded context relies on for a business decision.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

from backend.domain.crm.exceptions import InvalidCustomerTagError
from backend.shared.ids import new_uuid


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass(slots=True)
class CustomerTag:
    id: str
    code: str
    label: str
    active: bool = True
    created_at: str = field(default_factory=_utcnow)
    updated_at: str = field(default_factory=_utcnow)

    @classmethod
    def create(cls, code: str, label: str) -> "CustomerTag":
        if not code or not code.strip():
            raise InvalidCustomerTagError("code es obligatorio")
        if not label or not label.strip():
            raise InvalidCustomerTagError("label es obligatorio")
        return cls(id=new_uuid(), code=code.strip().upper(), label=label.strip())

    def deactivate(self) -> None:
        self.active = False
        self.updated_at = _utcnow()
