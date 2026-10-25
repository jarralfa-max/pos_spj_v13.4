"""FinanceAuditQueryService — bitácora de auditoría financiera (§25), sólo lectura."""

from __future__ import annotations

import json

from backend.application.queries.finance.base_finance_query_service import (
    FinanceQueryServiceBase,
)


class FinanceAuditQueryService(FinanceQueryServiceBase):
    def entries(self, *, entity_type: str | None = None, entity_id: str | None = None,
                action: str | None = None, user_id: str | None = None,
                date_from: str | None = None, date_to: str | None = None,
                limit: int = 200, offset: int = 0) -> list[dict]:
        conditions, params = ["1=1"], []
        for column, value in (("entity_type", entity_type), ("entity_id", entity_id),
                              ("action", action), ("user_id", user_id)):
            if value:
                conditions.append(f"{column} = ?")
                params.append(value)
        if date_from:
            conditions.append("occurred_at >= ?")
            params.append(date_from)
        if date_to:
            conditions.append("occurred_at <= ?")
            params.append(f"{date_to}T23:59:59")
        params.extend([limit, offset])
        rows = self._query(
            "SELECT id, action, entity_type, entity_id, operation_id, user_id, before_json,"
            " after_json, reason, branch_id, occurred_at FROM finance_audit_log"
            f" WHERE {' AND '.join(conditions)} ORDER BY occurred_at DESC LIMIT ? OFFSET ?",
            tuple(params))
        for row in rows:
            row["before"] = json.loads(row.pop("before_json") or "{}")
            row["after"] = json.loads(row.pop("after_json") or "{}")
        return rows
