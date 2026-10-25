"""BudgetQueryService — ejecución presupuestal y solicitudes de gasto (§16).

aprobado − comprometido − devengado − pagado = disponible, con el nivel de
control (AVAILABLE / WARNING / BLOCKING) calculado aquí, nunca en la pantalla.
"""

from __future__ import annotations

from decimal import Decimal

from backend.application.queries.finance.base_finance_query_service import (
    FinanceQueryServiceBase,
    decimal_sum,
    money_text,
)


class BudgetQueryService(FinanceQueryServiceBase):
    def _warning_percent(self) -> Decimal | None:
        row = self._query_one("SELECT setting_value FROM finance_settings"
                              " WHERE setting_key='budget_warning_percent'")
        return Decimal(row["setting_value"]) if row and row["setting_value"] else None

    def budget_execution(self, fiscal_year: int, *, budget_id: str | None = None) -> list[dict]:
        sql = ("SELECT b.id AS budget_id, b.name, b.status, b.version, b.blocking,"
               " bl.id AS line_id, bl.period_code, a.code AS account_code,"
               " a.name AS account_name, bl.planned_amount, bl.committed_amount,"
               " bl.accrued_amount, bl.paid_amount, bl.cost_center_id, bl.project_id,"
               " bl.department_id FROM budgets b JOIN budget_lines bl ON bl.budget_id = b.id"
               " JOIN accounts a ON a.id = bl.account_id WHERE b.fiscal_year = ?")
        params: list = [fiscal_year]
        if budget_id:
            sql += " AND b.id = ?"
            params.append(budget_id)
        else:
            sql += " AND b.status IN ('APPROVED','ACTIVE')"
        rows = self._query(sql + " ORDER BY bl.period_code, a.code", tuple(params))
        warning = self._warning_percent()
        for row in rows:
            planned = decimal_sum([row["planned_amount"]])
            consumed = decimal_sum([row["committed_amount"], row["accrued_amount"],
                                    row["paid_amount"]])
            row["consumed"] = money_text(consumed)
            row["available"] = money_text(planned - consumed)
            if consumed > planned:
                row["control_level"] = "BLOCKING"
            elif warning is not None and planned > 0 and consumed * 100 / planned >= warning:
                row["control_level"] = "WARNING"
            else:
                row["control_level"] = "AVAILABLE"
            row["consumed_percent"] = (format((consumed * 100 / planned).quantize(Decimal("0.1")),
                                              "f") if planned > 0 else "")
        return rows

    def list_budgets(self) -> list[dict]:
        return self._query(
            "SELECT id, name, fiscal_year, version, status, blocking, approved_by, approved_at,"
            " rejection_reason, previous_version_id FROM budgets"
            " ORDER BY fiscal_year DESC, name, version DESC")

    def expense_requests(self, *, status: str | None = None, limit: int = 200) -> list[dict]:
        sql = ("SELECT er.id, er.created_at, er.period_code, er.category, er.description,"
               " er.amount, er.accrued_amount, er.settled_amount, er.status,"
               " er.required_approvals, er.requested_by, er.document_reference,"
               " er.resolution_reason, a.code AS account_code, a.name AS account_name,"
               " (SELECT COUNT(*) FROM expense_approvals ap WHERE ap.expense_request_id = er.id"
               "  AND ap.decision='APPROVED') AS approvals"
               " FROM expense_requests er JOIN accounts a ON a.id = er.account_id")
        params: tuple = ()
        if status:
            sql += " WHERE er.status = ?"
            params = (status,)
        return self._query(sql + " ORDER BY er.created_at DESC LIMIT ?", params + (limit,))

    def approval_rules(self) -> list[dict]:
        return self._query("SELECT id, name, min_amount, branch_id, category, cost_center_id,"
                           " requester_id, required_approvals, priority FROM expense_approval_rules"
                           " WHERE active=1 ORDER BY priority DESC, min_amount")

    def budget_vs_actual(self, fiscal_year: int) -> list[dict]:
        """Por periodo: presupuestado contra ejercido (devengado + pagado)."""
        grouped: dict[str, dict] = {}
        for row in self.budget_execution(fiscal_year):
            bucket = grouped.setdefault(row["period_code"], {"planned": [], "actual": []})
            bucket["planned"].append(row["planned_amount"])
            bucket["actual"].extend([row["accrued_amount"], row["paid_amount"]])
        return [{"period_code": period, "planned": money_text(decimal_sum(v["planned"])),
                 "actual": money_text(decimal_sum(v["actual"]))}
                for period, v in sorted(grouped.items())]
