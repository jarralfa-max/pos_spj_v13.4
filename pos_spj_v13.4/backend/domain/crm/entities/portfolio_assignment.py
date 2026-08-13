"""PortfolioAssignment — one evidence record of a customer being placed in
a CustomerPortfolio (§33-36). Append-only, mirrors CustomerOwnership: moving
a customer to a different portfolio captures a new row rather than
overwriting the previous one, so the full "which cartera owned this account,
and when" history survives. The current portfolio for a customer is
resolved via PortfolioAssignmentRepositoryPort.get_latest().
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

from backend.domain.crm.exceptions import InvalidPortfolioAssignmentError
from backend.shared.ids import new_uuid


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass(slots=True)
class PortfolioAssignment:
    id: str
    customer_id: str
    portfolio_id: str
    assigned_by_user_id: str | None = None
    reason: str = ""
    operation_id: str | None = None
    created_at: str = field(default_factory=_utcnow)

    @classmethod
    def capture(
        cls, customer_id: str, portfolio_id: str, *,
        assigned_by_user_id: str | None = None, reason: str = "",
        operation_id: str | None = None,
    ) -> "PortfolioAssignment":
        if not customer_id:
            raise InvalidPortfolioAssignmentError("customer_id es obligatorio")
        if not portfolio_id:
            raise InvalidPortfolioAssignmentError("portfolio_id es obligatorio")
        return cls(
            id=new_uuid(), customer_id=customer_id, portfolio_id=portfolio_id,
            assigned_by_user_id=assigned_by_user_id, reason=reason.strip(),
            operation_id=operation_id,
        )
