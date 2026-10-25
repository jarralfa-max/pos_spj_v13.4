"""AuthorizeCloseExceptionUseCase — acepta una diferencia material con motivo.

Quien llama exige ``FINANZAS.periodo.autorizar_excepcion``. Queda quién y por qué.
"""

from __future__ import annotations

from backend.domain.finance.enums import AuditAction
from backend.domain.finance.exceptions import FinanceDomainError
from backend.infrastructure.db.repositories.finance.unit_of_work import FinanceUnitOfWork


class AuthorizeCloseExceptionUseCase:
    def execute(self, connection, *, exception_id: str, authorized_by: str, reason: str,
                operation_id: str | None = None) -> None:
        if not (reason or "").strip():
            raise FinanceDomainError("Autorizar una diferencia exige el motivo")
        with FinanceUnitOfWork(connection) as uow:
            uow.close_exceptions.authorize(exception_id, authorized_by=authorized_by,
                                           reason=reason.strip())
            uow.audit(AuditAction.PERIOD_CLOSED, entity_type="close_exception",
                      entity_id=exception_id, operation_id=operation_id or exception_id,
                      user_id=authorized_by, after={"status": "AUTHORIZED"},
                      reason=reason.strip())
