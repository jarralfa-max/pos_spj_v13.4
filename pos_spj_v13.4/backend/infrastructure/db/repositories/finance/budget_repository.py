"""Budget repository."""

from __future__ import annotations

from backend.domain.finance.entities.budget import Budget, BudgetLine
from backend.domain.finance.enums import BudgetStatus
from backend.domain.finance.value_objects.money import Money
from backend.infrastructure.db.repositories.finance.base import FinanceRepositoryBase

_COLUMNS = ("id, name, fiscal_year, version, status, submitted_by, approved_by,"
            " approved_at, branch_id, operation_id, created_at, updated_at")
_LINE_COLUMNS = ("id, budget_id, account_id, period_code, planned_amount,"
                 " committed_amount, accrued_amount, currency_code, cost_center_id, branch_id")


class BudgetRepository(FinanceRepositoryBase):
    def save(self, budget: Budget) -> None:
        self._execute(
            f"INSERT INTO budgets ({_COLUMNS}) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
            (budget.id, budget.name, budget.fiscal_year, budget.version,
             budget.status.value, budget.submitted_by, budget.approved_by,
             budget.approved_at, budget.branch_id, budget.operation_id,
             budget.created_at, budget.updated_at),
        )
        self._sync_lines(budget)

    def update(self, budget: Budget) -> None:
        self._execute(
            "UPDATE budgets SET status=?, submitted_by=?, approved_by=?, approved_at=?,"
            " updated_at=? WHERE id=?",
            (budget.status.value, budget.submitted_by, budget.approved_by,
             budget.approved_at, budget.updated_at, budget.id),
        )
        self._sync_lines(budget)

    def _sync_lines(self, budget: Budget) -> None:
        existing = {
            row["id"] for row in self._query(
                "SELECT id FROM budget_lines WHERE budget_id=?", (budget.id,)
            )
        }
        for line in budget.lines:
            if line.id in existing:
                self._execute(
                    "UPDATE budget_lines SET planned_amount=?, committed_amount=?,"
                    " accrued_amount=? WHERE id=?",
                    (line.planned_amount.to_string(), line.committed_amount.to_string(),
                     line.accrued_amount.to_string(), line.id),
                )
            else:
                self._execute(
                    f"INSERT INTO budget_lines ({_LINE_COLUMNS}) VALUES (?,?,?,?,?,?,?,?,?,?)",
                    (line.id, line.budget_id, line.account_id, line.period_code,
                     line.planned_amount.to_string(), line.committed_amount.to_string(),
                     line.accrued_amount.to_string(), line.planned_amount.currency_code,
                     line.cost_center_id, line.branch_id),
                )

    def get(self, budget_id: str) -> Budget | None:
        row = self._query_one(f"SELECT {_COLUMNS} FROM budgets WHERE id=?", (budget_id,))
        return self._hydrate(row) if row else None

    def find_by_operation_id(self, operation_id: str) -> Budget | None:
        row = self._query_one(
            f"SELECT {_COLUMNS} FROM budgets WHERE operation_id=?", (operation_id,)
        )
        return self._hydrate(row) if row else None

    def find_approved_for_year(self, fiscal_year: int, branch_id: str | None = None) -> Budget | None:
        if branch_id is None:
            row = self._query_one(
                f"SELECT {_COLUMNS} FROM budgets WHERE fiscal_year=? AND status='APPROVED'"
                " ORDER BY version DESC LIMIT 1",
                (fiscal_year,),
            )
        else:
            row = self._query_one(
                f"SELECT {_COLUMNS} FROM budgets WHERE fiscal_year=? AND status='APPROVED'"
                " AND (branch_id=? OR branch_id IS NULL) ORDER BY version DESC LIMIT 1",
                (fiscal_year, branch_id),
            )
        return self._hydrate(row) if row else None

    def list_all(self) -> list[Budget]:
        rows = self._query(f"SELECT {_COLUMNS} FROM budgets ORDER BY fiscal_year DESC, version DESC")
        return [self._hydrate(row) for row in rows]

    def _hydrate(self, row: dict) -> Budget:
        budget = Budget(
            id=row["id"], name=row["name"], fiscal_year=row["fiscal_year"],
            version=row["version"], operation_id=row["operation_id"],
            status=BudgetStatus(row["status"]),
            submitted_by=row["submitted_by"], approved_by=row["approved_by"],
            approved_at=row["approved_at"], branch_id=row["branch_id"],
            created_at=row["created_at"], updated_at=row["updated_at"],
        )
        for line_row in self._query(
            f"SELECT {_LINE_COLUMNS} FROM budget_lines WHERE budget_id=? ORDER BY period_code",
            (row["id"],),
        ):
            currency = line_row["currency_code"]
            budget.lines.append(BudgetLine(
                id=line_row["id"], budget_id=line_row["budget_id"],
                account_id=line_row["account_id"], period_code=line_row["period_code"],
                planned_amount=Money.from_string(line_row["planned_amount"], currency),
                committed_amount=Money.from_string(line_row["committed_amount"], currency),
                accrued_amount=Money.from_string(line_row["accrued_amount"], currency),
                cost_center_id=line_row["cost_center_id"], branch_id=line_row["branch_id"],
            ))
        return budget
