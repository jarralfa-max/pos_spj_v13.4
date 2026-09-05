"""Outbound integration ports for the forecasting bounded context (BI-14).

BI-0 found a legacy forecast service calling the Treasury module's
account-status method directly — a violation of §10 ("BI no debe depender
directo de Tesorería"). `FinanceQueryPort` is the fix: any estimated cost or
capital figure a recommendation needs comes through this port, never a
concrete Finance/Treasury import. An infrastructure adapter (future phase)
implements it against `FinanceAnalyticsQueryService` or similar; nothing in
`backend/domain` or `backend/application/forecasting` may import
Finance/Treasury modules concretely — see
`tests/architecture/test_forecasting_never_imports_treasury_directly.py`.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Protocol


class FinanceQueryPort(Protocol):
    def estimate_purchase_cost(
        self, product_id: str, quantity: Decimal, branch_id: str
    ) -> Decimal | None:
        """Best-effort cost estimate; `None` if unknown (never fabricated)."""
        ...


class ProductionCapacityPort(Protocol):
    """Outbound port toward Meat Processing/Manufacturing (§76, BI-15) — same
    principle as `FinanceQueryPort`: forecasting never owns yield/capacity
    data, it only asks for it."""

    def expected_yield_pct(self, product_id: str, branch_id: str) -> Decimal | None:
        """Fraction in (0, 1]; `None` if unknown (never assumed to be 1.0)."""
        ...

    def available_capacity(self, branch_id: str, as_of: date) -> Decimal | None:
        """Production capacity (same unit as the product's demand series)
        available on `as_of`; `None` if unknown."""
        ...
