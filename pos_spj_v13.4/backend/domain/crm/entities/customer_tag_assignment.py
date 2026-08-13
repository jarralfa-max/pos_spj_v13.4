"""CustomerTagAssignment — a tag attached to a customer (§33-36). Append-
only-with-nullable-removed_at, mirrors CustomerSegmentMembership: attaching
a tag inserts a new row; removing it sets ``removed_at`` rather than
deleting. Unlike segment membership, a tag assignment has no ``source`` —
tags are always applied by a user action, never rule/analytics-derived
(§33-36: tags "no sustituyen estatus/segmento/riesgo/consentimiento/
territorio", i.e. they carry no business-rule weight of their own).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

from backend.domain.crm.exceptions import InvalidCustomerTagAssignmentError
from backend.shared.ids import new_uuid


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass(slots=True)
class CustomerTagAssignment:
    id: str
    customer_id: str
    tag_id: str
    assigned_by_user_id: str | None = None
    removed_at: str | None = None
    removed_by_user_id: str | None = None
    operation_id: str | None = None
    created_at: str = field(default_factory=_utcnow)

    @classmethod
    def add(
        cls, customer_id: str, tag_id: str, *,
        assigned_by_user_id: str | None = None, operation_id: str | None = None,
    ) -> "CustomerTagAssignment":
        if not customer_id:
            raise InvalidCustomerTagAssignmentError("customer_id es obligatorio")
        if not tag_id:
            raise InvalidCustomerTagAssignmentError("tag_id es obligatorio")
        return cls(
            id=new_uuid(), customer_id=customer_id, tag_id=tag_id,
            assigned_by_user_id=assigned_by_user_id, operation_id=operation_id,
        )

    def remove(self, removed_by_user_id: str | None = None) -> None:
        if self.removed_at is not None:
            raise InvalidCustomerTagAssignmentError("Esta etiqueta ya fue removida")
        self.removed_at = _utcnow()
        self.removed_by_user_id = removed_by_user_id

    def is_active(self) -> bool:
        return self.removed_at is None
