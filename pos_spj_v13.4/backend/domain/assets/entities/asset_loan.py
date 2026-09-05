"""AssetLoan — temporary loan of an asset (ASSET-4, §21).

Distinct from AssetAssignment: a loan always has an expected return date and
an authorizer, and is tracked separately even though ``TEMPORARY_LOAN`` also
exists as an AssetAssignmentType for custody-history purposes.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timezone

from backend.domain.assets.exceptions import AssetDomainError, AssetStateInvalidError
from backend.shared.ids import new_uuid


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass(slots=True)
class AssetLoan:
    id: str
    asset_id: str
    borrower: str
    expected_return_at: date
    authorized_by: str
    operation_id: str
    condition_out: str | None = None
    condition_in: str | None = None
    checkout_at: str = field(default_factory=_utcnow)
    returned_at: str | None = None

    @classmethod
    def create(cls, asset_id: str, borrower: str, expected_return_at: date,
               authorized_by: str, operation_id: str, *,
               condition_out: str | None = None) -> "AssetLoan":
        if not asset_id:
            raise AssetDomainError("AssetLoan.asset_id is required")
        if not borrower:
            raise AssetDomainError("AssetLoan.borrower is required")
        if not authorized_by:
            raise AssetDomainError("AssetLoan.authorized_by is required")
        return cls(
            id=new_uuid(), asset_id=asset_id, borrower=borrower,
            expected_return_at=expected_return_at, authorized_by=authorized_by,
            operation_id=operation_id, condition_out=condition_out,
        )

    def is_returned(self) -> bool:
        return self.returned_at is not None

    def is_overdue(self, *, as_of: date | None = None) -> bool:
        if self.is_returned():
            return False
        return (as_of or date.today()) > self.expected_return_at

    def return_loan(self, condition_in: str | None = None) -> None:
        if self.returned_at is not None:
            raise AssetStateInvalidError("Este préstamo ya fue devuelto")
        self.returned_at = _utcnow()
        self.condition_in = condition_in
