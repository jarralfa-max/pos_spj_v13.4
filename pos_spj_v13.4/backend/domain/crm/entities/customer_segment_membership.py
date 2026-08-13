"""CustomerSegmentMembership — a customer's membership in a CustomerSegment
(§33-36). Append-only-with-nullable-removed_at: adding a customer to a
segment inserts a new row; removing sets ``removed_at`` rather than
deleting, so segment history ("was this customer ever in segment X, and for
how long") survives. ``source`` records how *this particular* membership
came to be (§33-36: "MANUAL, RULE_BASED, IMPORTED, ANALYTICS_GENERATED") —
see CustomerSegment's docstring for why the source lives on the membership
and not on the segment itself.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

from backend.domain.crm.enums import SegmentMembershipSource
from backend.domain.crm.exceptions import InvalidCustomerSegmentMembershipError
from backend.shared.ids import new_uuid


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass(slots=True)
class CustomerSegmentMembership:
    id: str
    customer_id: str
    segment_id: str
    source: SegmentMembershipSource = SegmentMembershipSource.MANUAL
    added_by_user_id: str | None = None
    removed_at: str | None = None
    removed_by_user_id: str | None = None
    operation_id: str | None = None
    created_at: str = field(default_factory=_utcnow)

    @classmethod
    def add(
        cls, customer_id: str, segment_id: str,
        source: SegmentMembershipSource = SegmentMembershipSource.MANUAL, *,
        added_by_user_id: str | None = None, operation_id: str | None = None,
    ) -> "CustomerSegmentMembership":
        if not customer_id:
            raise InvalidCustomerSegmentMembershipError("customer_id es obligatorio")
        if not segment_id:
            raise InvalidCustomerSegmentMembershipError("segment_id es obligatorio")
        return cls(
            id=new_uuid(), customer_id=customer_id, segment_id=segment_id, source=source,
            added_by_user_id=added_by_user_id, operation_id=operation_id,
        )

    def remove(self, removed_by_user_id: str | None = None) -> None:
        if self.removed_at is not None:
            raise InvalidCustomerSegmentMembershipError(
                "Esta membresía de segmento ya fue removida")
        self.removed_at = _utcnow()
        self.removed_by_user_id = removed_by_user_id

    def is_active(self) -> bool:
        return self.removed_at is None
