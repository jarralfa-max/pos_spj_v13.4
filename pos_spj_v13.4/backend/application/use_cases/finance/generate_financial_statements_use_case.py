"""GenerateFinancialStatementsUseCase — produces the four statements and
publishes FINANCIAL_STATEMENTS_GENERATED."""

from __future__ import annotations

import dataclasses
import json

from backend.application.queries.finance.financial_statement_query_service import (
    FinancialStatementQueryService,
)
from backend.infrastructure.db.repositories.finance.unit_of_work import FinanceUnitOfWork
from backend.shared.events.event_names import EventName
from backend.shared.ids import new_uuid


class GenerateFinancialStatementsUseCase:
    def execute(self, connection, *, date_from: str, date_to: str,
                branch_id: str | None = None, operation_id: str) -> dict:
        query = FinancialStatementQueryService(connection)
        statements = {
            "trial_balance": [dataclasses.asdict(row) for row in query.trial_balance(
                date_from=date_from, date_to=date_to, branch_id=branch_id)],
            "balance_sheet": query.balance_sheet(as_of=date_to, branch_id=branch_id),
            "income_statement": query.income_statement(
                date_from=date_from, date_to=date_to, branch_id=branch_id),
            "cash_flow_statement": query.cash_flow_statement(
                date_from=date_from, date_to=date_to, branch_id=branch_id),
            "period": {"from": date_from, "to": date_to, "branch_id": branch_id},
        }
        with FinanceUnitOfWork(connection) as uow:
            uow.outbox.enqueue(
                event_id=new_uuid(),
                event_name=EventName.FINANCIAL_STATEMENTS_GENERATED.value,
                payload_json=json.dumps({"from": date_from, "to": date_to,
                                         "branch_id": branch_id}),
                operation_id=operation_id,
            )
        return statements
