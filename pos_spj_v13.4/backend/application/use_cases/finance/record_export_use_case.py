"""RecordFinanceExportUseCase — toda exportación de información financiera queda auditada (§25)."""

from __future__ import annotations

from backend.domain.finance.enums import AuditAction
from backend.infrastructure.db.repositories.finance.unit_of_work import FinanceUnitOfWork
from backend.shared.ids import new_uuid


class RecordFinanceExportUseCase:
    def __call__(self, connection, *, action: AuditAction, what: str, file_name: str,
                 rows: int, user_id: str) -> None:
        operation_id = new_uuid()
        with FinanceUnitOfWork(connection) as uow:
            uow.audit(action, entity_type="export", entity_id=operation_id,
                      operation_id=operation_id, user_id=user_id,
                      after={"what": what, "file_name": file_name, "rows": rows})
