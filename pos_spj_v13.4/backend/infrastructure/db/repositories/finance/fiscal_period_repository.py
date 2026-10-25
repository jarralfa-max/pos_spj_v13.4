"""FiscalPeriod repository."""

from __future__ import annotations

from datetime import date

from backend.domain.finance.entities.fiscal_period import FiscalPeriod
from backend.domain.finance.enums import FiscalPeriodStatus
from backend.infrastructure.db.repositories.finance.base import FinanceRepositoryBase


def _to_entity(row: dict) -> FiscalPeriod:
    return FiscalPeriod(
        id=row["id"], year=row["year"], month=row["month"],
        status=FiscalPeriodStatus(row["status"]),
        opened_at=row["opened_at"], soft_closed_at=row["soft_closed_at"],
        soft_closed_by=row["soft_closed_by"],
        closed_at=row["closed_at"], closed_by=row["closed_by"],
        reopened_at=row["reopened_at"], reopened_by=row["reopened_by"],
        reopen_reason=row["reopen_reason"],
        created_at=row["created_at"], updated_at=row["updated_at"],
    )


def _mutable(period: FiscalPeriod) -> dict:
    return {
        "status": period.status.value, "soft_closed_at": period.soft_closed_at,
        "soft_closed_by": period.soft_closed_by, "closed_at": period.closed_at,
        "closed_by": period.closed_by, "reopened_at": period.reopened_at,
        "reopened_by": period.reopened_by, "reopen_reason": period.reopen_reason,
        "updated_at": period.updated_at,
    }


class FiscalPeriodRepository(FinanceRepositoryBase):
    def save(self, period: FiscalPeriod) -> None:
        values = {"id": period.id, "year": period.year, "month": period.month,
                  "opened_at": period.opened_at, "created_at": period.created_at}
        values.update(_mutable(period))
        self._insert("fiscal_periods", values)

    def update(self, period: FiscalPeriod) -> None:
        self._update("fiscal_periods", _mutable(period), where="id=?", params=(period.id,))

    def get(self, period_id: str) -> FiscalPeriod | None:
        row = self._query_one("SELECT * FROM fiscal_periods WHERE id=?", (period_id,))
        return _to_entity(row) if row else None

    def find_for_date(self, value: date) -> FiscalPeriod | None:
        return self.find_by_code(value.year, value.month)

    def find_by_code(self, year: int, month: int) -> FiscalPeriod | None:
        row = self._query_one("SELECT * FROM fiscal_periods WHERE year=? AND month=?",
                              (year, month))
        return _to_entity(row) if row else None

    def list_all(self) -> list[FiscalPeriod]:
        return [_to_entity(row) for row in
                self._query("SELECT * FROM fiscal_periods ORDER BY year, month")]
