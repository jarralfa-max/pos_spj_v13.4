"""CustomerDataQualityIssueRepository — persists detected data-quality
issues. Mirrors customer_duplicate_candidate_repository.py.
"""

from __future__ import annotations

from backend.domain.customers.entities.customer_data_quality_issue import (
    CustomerDataQualityIssue,
)
from backend.domain.customers.enums import DataQualityIssueStatus, DataQualityRuleCode
from backend.infrastructure.db.repositories.customers.base import CustomerRepositoryBase

_COLS = (
    "id, customer_id, rule_code, description, status, acknowledged_by_user_id,"
    " acknowledged_at, corrected_at, dismissed_by_user_id, dismissed_at,"
    " dismissal_reason, operation_id, created_at, updated_at"
)


class CustomerDataQualityIssueRepository(CustomerRepositoryBase):
    def save(self, issue: CustomerDataQualityIssue, *,
             operation_id: str | None = None) -> None:
        self._execute(
            f"INSERT INTO customer_data_quality_issues ({_COLS})"
            " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            self._params(issue, operation_id or issue.operation_id))

    def update(self, issue: CustomerDataQualityIssue) -> None:
        self._execute(
            "UPDATE customer_data_quality_issues SET status=?, acknowledged_by_user_id=?,"
            " acknowledged_at=?, corrected_at=?, dismissed_by_user_id=?, dismissed_at=?,"
            " dismissal_reason=?, updated_at=? WHERE id=?",
            (issue.status.value, issue.acknowledged_by_user_id, issue.acknowledged_at,
             issue.corrected_at, issue.dismissed_by_user_id, issue.dismissed_at,
             issue.dismissal_reason, issue.updated_at, issue.id))

    def get(self, issue_id: str) -> CustomerDataQualityIssue | None:
        row = self._query_one(f"SELECT {_COLS} FROM customer_data_quality_issues WHERE id=?",
                              (issue_id,))
        return self._hydrate(row) if row else None

    def get_open(self, customer_id: str, rule_code: str) -> CustomerDataQualityIssue | None:
        row = self._query_one(
            f"SELECT {_COLS} FROM customer_data_quality_issues"
            " WHERE customer_id=? AND rule_code=? AND status IN ('OPEN','ACKNOWLEDGED')"
            " LIMIT 1", (customer_id, rule_code))
        return self._hydrate(row) if row else None

    def list_open_for_customer(self, customer_id: str) -> list[CustomerDataQualityIssue]:
        rows = self._query(
            f"SELECT {_COLS} FROM customer_data_quality_issues"
            " WHERE customer_id=? AND status IN ('OPEN','ACKNOWLEDGED')"
            " ORDER BY created_at DESC", (customer_id,))
        return [self._hydrate(r) for r in rows]

    def list_by_status(self, status: str) -> list[CustomerDataQualityIssue]:
        rows = self._query(
            f"SELECT {_COLS} FROM customer_data_quality_issues"
            " WHERE status=? ORDER BY created_at DESC", (status,))
        return [self._hydrate(r) for r in rows]

    @staticmethod
    def _params(issue: CustomerDataQualityIssue, operation_id: str | None) -> tuple:
        return (
            issue.id, issue.customer_id, issue.rule_code.value, issue.description,
            issue.status.value, issue.acknowledged_by_user_id, issue.acknowledged_at,
            issue.corrected_at, issue.dismissed_by_user_id, issue.dismissed_at,
            issue.dismissal_reason, operation_id, issue.created_at, issue.updated_at,
        )

    @staticmethod
    def _hydrate(row: dict) -> CustomerDataQualityIssue:
        return CustomerDataQualityIssue(
            id=row["id"], customer_id=row["customer_id"],
            rule_code=DataQualityRuleCode(row["rule_code"]), description=row["description"] or "",
            status=DataQualityIssueStatus(row["status"]),
            acknowledged_by_user_id=row["acknowledged_by_user_id"],
            acknowledged_at=row["acknowledged_at"], corrected_at=row["corrected_at"],
            dismissed_by_user_id=row["dismissed_by_user_id"], dismissed_at=row["dismissed_at"],
            dismissal_reason=row["dismissal_reason"] or "", operation_id=row["operation_id"],
            created_at=row["created_at"], updated_at=row["updated_at"],
        )
