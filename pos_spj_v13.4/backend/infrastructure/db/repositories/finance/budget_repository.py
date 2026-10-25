"""Budget repository (§16)."""

from __future__ import annotations

from backend.domain.finance.entities.budget import Budget, BudgetLine
from backend.domain.finance.enums import BudgetStatus, CONTROLLING_BUDGET_STATUSES, sql_in
from backend.domain.finance.exceptions import ConcurrencyConflictError
from backend.domain.finance.value_objects.money import Money
from backend.infrastructure.db.repositories.finance.base import FinanceRepositoryBase

_CONTROLLING = sql_in(CONTROLLING_BUDGET_STATUSES)


def _mutable(budget: Budget) -> dict:
    return {
        "status": budget.status.value, "blocking": int(budget.blocking),
        "submitted_by": budget.submitted_by, "approved_by": budget.approved_by,
        "approved_at": budget.approved_at, "rejection_reason": budget.rejection_reason,
        "cancel_reason": budget.cancel_reason, "updated_at": budget.updated_at,
    }


def _line_amounts(line: BudgetLine) -> dict:
    return {
        "planned_amount": line.planned_amount.to_string(),
        "committed_amount": line.committed_amount.to_string(),
        "accrued_amount": line.accrued_amount.to_string(),
        "paid_amount": line.paid_amount.to_string(),
    }


class BudgetRepository(FinanceRepositoryBase):
    def save(self, budget: Budget) -> None:
        values = {"id": budget.id, "name": budget.name, "fiscal_year": budget.fiscal_year,
                  "version": budget.version, "previous_version_id": budget.previous_version_id,
                  "branch_id": budget.branch_id, "operation_id": budget.operation_id,
                  "row_version": budget.row_version, "created_at": budget.created_at}
        values.update(_mutable(budget))
        self._insert("budgets", values)
        self._sync_lines(budget)

    def update(self, budget: Budget) -> None:
        values = _mutable(budget)
        values["row_version"] = budget.row_version + 1
        cursor = self._update("budgets", values, where="id=? AND row_version=?",
                              params=(budget.id, budget.row_version))
        if cursor.rowcount == 0:
            raise ConcurrencyConflictError(
                f"El presupuesto {budget.id} cambió desde que se leyó; recargue")
        budget.row_version += 1
        self._sync_lines(budget)

    def _sync_lines(self, budget: Budget) -> None:
        existing = {row["id"] for row in self._query(
            "SELECT id FROM budget_lines WHERE budget_id=?", (budget.id,))}
        for line in budget.lines:
            if line.id in existing:
                self._update("budget_lines", _line_amounts(line), where="id=?",
                             params=(line.id,))
                continue
            values = {
                "id": line.id, "budget_id": line.budget_id, "account_id": line.account_id,
                "period_code": line.period_code,
                "currency_code": line.planned_amount.currency_code,
                "cost_center_id": line.cost_center_id,
                "profit_center_id": line.profit_center_id, "project_id": line.project_id,
                "department_id": line.department_id, "branch_id": line.branch_id,
            }
            values.update(_line_amounts(line))
            self._insert("budget_lines", values)

    def get(self, budget_id: str) -> Budget | None:
        row = self._query_one("SELECT * FROM budgets WHERE id=?", (budget_id,))
        return self._hydrate(row) if row else None

    def find_by_operation_id(self, operation_id: str) -> Budget | None:
        row = self._query_one("SELECT * FROM budgets WHERE operation_id=?", (operation_id,))
        return self._hydrate(row) if row else None

    def find_approved_for_year(self, fiscal_year: int,
                               branch_id: str | None = None) -> Budget | None:
        """El presupuesto que controla el gasto del año (aprobado o activo, última versión)."""
        if branch_id is None:
            row = self._query_one(
                f"SELECT * FROM budgets WHERE fiscal_year=? AND status IN {_CONTROLLING}"
                " ORDER BY version DESC LIMIT 1", (fiscal_year,))
        else:
            row = self._query_one(
                f"SELECT * FROM budgets WHERE fiscal_year=? AND status IN {_CONTROLLING}"
                " AND (branch_id=? OR branch_id IS NULL)"
                " ORDER BY (branch_id IS NULL), version DESC LIMIT 1",
                (fiscal_year, branch_id))
        return self._hydrate(row) if row else None

    def next_version(self, name: str, fiscal_year: int) -> int:
        row = self._query_one(
            "SELECT version FROM budgets WHERE name=? AND fiscal_year=?"
            " ORDER BY version DESC LIMIT 1", (name, fiscal_year))
        return int(row["version"]) + 1 if row else 1

    def list_all(self) -> list[Budget]:
        return [self._hydrate(r) for r in self._query(
            "SELECT * FROM budgets ORDER BY fiscal_year DESC, version DESC")]

    def _hydrate(self, row: dict) -> Budget:
        budget = Budget(
            id=row["id"], name=row["name"], fiscal_year=row["fiscal_year"],
            version=row["version"], operation_id=row["operation_id"],
            status=BudgetStatus(row["status"]), blocking=bool(row["blocking"]),
            previous_version_id=row["previous_version_id"],
            submitted_by=row["submitted_by"], approved_by=row["approved_by"],
            approved_at=row["approved_at"], rejection_reason=row["rejection_reason"],
            cancel_reason=row["cancel_reason"], branch_id=row["branch_id"],
            created_at=row["created_at"], updated_at=row["updated_at"],
            row_version=int(row["row_version"] or 0),
        )
        for line_row in self._query(
                "SELECT * FROM budget_lines WHERE budget_id=? ORDER BY period_code",
                (row["id"],)):
            currency = line_row["currency_code"]
            budget.lines.append(BudgetLine(
                id=line_row["id"], budget_id=line_row["budget_id"],
                account_id=line_row["account_id"], period_code=line_row["period_code"],
                planned_amount=Money.from_string(line_row["planned_amount"], currency),
                committed_amount=Money.from_string(line_row["committed_amount"], currency),
                accrued_amount=Money.from_string(line_row["accrued_amount"], currency),
                paid_amount=Money.from_string(line_row["paid_amount"], currency),
                cost_center_id=line_row["cost_center_id"], branch_id=line_row["branch_id"],
                profit_center_id=line_row["profit_center_id"],
                project_id=line_row["project_id"], department_id=line_row["department_id"],
            ))
        return budget
