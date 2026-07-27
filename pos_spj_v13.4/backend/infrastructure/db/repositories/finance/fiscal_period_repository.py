"""FiscalPeriod repository."""

from __future__ import annotations

from datetime import date

from backend.domain.finance.entities.fiscal_period import FiscalPeriod
from backend.domain.finance.enums import FiscalPeriodStatus
from backend.infrastructure.db.repositories.finance.base import FinanceRepositoryBase

_COLUMNS = ("id, year, month, status, opened_at, soft_closed_at, closed_at,"
            " reopened_at, closed_by, reopen_reason, created_at, updated_at")


def _to_entity(row: dict) -> FiscalPeriod:
    return FiscalPeriod(
        id=row["id"], year=row["year"], month=row["month"],
        status=FiscalPeriodStatus(row["status"]),
        opened_at=row["opened_at"], soft_closed_at=row["soft_closed_at"],
        closed_at=row["closed_at"], reopened_at=row["reopened_at"],
        closed_by=row["closed_by"], reopen_reason=row["reopen_reason"],
        created_at=row["created_at"], updated_at=row["updated_at"],
    )


class FiscalPeriodRepository(FinanceRepositoryBase):
    def save(self, period: FiscalPeriod) -> None:
        self._execute(
            f"INSERT INTO fiscal_periods ({_COLUMNS}) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
            (period.id, period.year, period.month, period.status.value, period.opened_at,
             period.soft_closed_at, period.closed_at, period.reopened_at,
             period.closed_by, period.reopen_reason, period.created_at, period.updated_at),
        )

    def update(self, period: FiscalPeriod) -> None:
        self._execute(
            "UPDATE fiscal_periods SET status=?, soft_closed_at=?, closed_at=?,"
            " reopened_at=?, closed_by=?, reopen_reason=?, updated_at=? WHERE id=?",
            (period.status.value, period.soft_closed_at, period.closed_at,
             period.reopened_at, period.closed_by, period.reopen_reason,
             period.updated_at, period.id),
        )

    def get(self, period_id: str) -> FiscalPeriod | None:
        row = self._query_one(f"SELECT {_COLUMNS} FROM fiscal_periods WHERE id=?", (period_id,))
        return _to_entity(row) if row else None

    def find_for_date(self, value: date) -> FiscalPeriod | None:
        return self.find_by_code(value.year, value.month)

    def find_by_code(self, year: int, month: int) -> FiscalPeriod | None:
        row = self._query_one(
            f"SELECT {_COLUMNS} FROM fiscal_periods WHERE year=? AND month=?", (year, month)
        )
        return _to_entity(row) if row else None

    def list_all(self) -> list[FiscalPeriod]:
        rows = self._query(f"SELECT {_COLUMNS} FROM fiscal_periods ORDER BY year, month")
        return [_to_entity(row) for row in rows]
