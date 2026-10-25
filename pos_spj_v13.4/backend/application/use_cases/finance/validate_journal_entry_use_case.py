"""ValidateJournalEntryUseCase — un borrador cuadrado y con cuentas válidas pasa a VALIDADO."""

from __future__ import annotations

from backend.domain.finance.enums import AuditAction
from backend.domain.finance.exceptions import AccountNotFoundError, JournalEntryNotFoundError
from backend.domain.finance.policies.balanced_entry_policy import BalancedEntryPolicy
from backend.infrastructure.db.repositories.finance.unit_of_work import FinanceUnitOfWork


class ValidateJournalEntryUseCase:
    def execute(self, connection, *, journal_entry_id: str, operation_id: str,
                validated_by: str):
        with FinanceUnitOfWork(connection) as uow:
            entry = uow.journal_entries.get(journal_entry_id)
            if entry is None:
                raise JournalEntryNotFoundError("El asiento no existe")
            for line in entry.lines:
                account = uow.accounts.get(line.account_id)
                if account is None:
                    raise AccountNotFoundError(f"La cuenta {line.account_id} no existe")
                account.assert_postable(branch_id=line.branch_id or entry.branch_id)
            BalancedEntryPolicy().enforce(entry)
            entry.validate(validated_by)
            uow.journal_entries.update_draft(entry)
            uow.audit(AuditAction.JOURNAL_ENTRY_VALIDATED, entity_type="journal_entry",
                      entity_id=entry.id, operation_id=operation_id, user_id=validated_by,
                      after={"status": entry.status.value,
                             "debits": entry.base_total_debits().to_string()},
                      branch_id=entry.branch_id)
            return entry
