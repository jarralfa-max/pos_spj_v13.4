"""MarkOverdueDocumentsUseCase — barrido de vencimientos de CxC y CxP (§11, §12).

Una CxC/CxP abierta cuyo vencimiento pasó queda OVERDUE y publica
RECEIVABLE_OVERDUE / PAYABLE_OVERDUE una sola vez (sólo al cambiar de estado).
Idempotente: correrlo dos veces el mismo día no cambia nada.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from backend.application.services.finance.posting_engine import publish_finance_event
from backend.infrastructure.db.repositories.finance.unit_of_work import FinanceUnitOfWork
from backend.shared.events.event_names import EventName
from backend.shared.ids import new_uuid


@dataclass(frozen=True, slots=True)
class OverdueSweepResult:
    receivables: int
    payables: int


class MarkOverdueDocumentsUseCase:
    def execute(self, connection, *, as_of: date) -> OverdueSweepResult:
        receivables = payables = 0
        with FinanceUnitOfWork(connection) as uow:
            for receivable in uow.receivables.list_overdue_candidates(as_of):
                if receivable.mark_overdue(as_of):
                    uow.receivables.update(receivable)
                    receivables += 1
                    publish_finance_event(uow, EventName.RECEIVABLE_OVERDUE, {
                        "receivable_id": receivable.id, "customer_id": receivable.customer_id,
                        "outstanding": receivable.outstanding_amount.to_string(),
                        "due_date": receivable.due_date.isoformat(),
                        "days_overdue": receivable.days_overdue(as_of),
                    }, operation_id=new_uuid(), entity_id=receivable.id,
                        branch_id=receivable.branch_id)
            for payable in uow.payables.list_overdue_candidates(as_of):
                if payable.mark_overdue(as_of):
                    uow.payables.update(payable)
                    payables += 1
                    publish_finance_event(uow, EventName.PAYABLE_OVERDUE, {
                        "payable_id": payable.id, "supplier_id": payable.supplier_id,
                        "outstanding": payable.outstanding_amount.to_string(),
                        "due_date": payable.due_date.isoformat(),
                    }, operation_id=new_uuid(), entity_id=payable.id,
                        branch_id=payable.branch_id)
        return OverdueSweepResult(receivables, payables)
