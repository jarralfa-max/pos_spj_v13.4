"""CustomerSegment — the configurable segment catalog (§33-36). "BI puede
sugerir, CRM administra el uso operativo" — ``rule_definition`` is an inert
text field for RULE_BASED segments: CRM stores and displays it but never
parses or executes it (BI owns rule evaluation and reports memberships back
via CustomerSegmentMembership.add(source=RULE_BASED/ANALYTICS_GENERATED)).
Which source produced a given membership is tracked per-membership, not
here — see CustomerSegmentMembership.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

from backend.domain.crm.exceptions import InvalidCustomerSegmentError
from backend.shared.ids import new_uuid


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass(slots=True)
class CustomerSegment:
    id: str
    code: str
    name: str
    description: str = ""
    rule_definition: str = ""
    active: bool = True
    created_at: str = field(default_factory=_utcnow)
    updated_at: str = field(default_factory=_utcnow)

    @classmethod
    def create(cls, code: str, name: str, *, description: str = "",
               rule_definition: str = "") -> "CustomerSegment":
        if not code or not code.strip():
            raise InvalidCustomerSegmentError("code es obligatorio")
        if not name or not name.strip():
            raise InvalidCustomerSegmentError("name es obligatorio")
        return cls(id=new_uuid(), code=code.strip().upper(), name=name.strip(),
                    description=description.strip(), rule_definition=rule_definition.strip())

    def deactivate(self) -> None:
        self.active = False
        self.updated_at = _utcnow()
