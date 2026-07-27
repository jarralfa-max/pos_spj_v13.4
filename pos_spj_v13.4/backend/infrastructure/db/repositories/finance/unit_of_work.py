"""FinanceUnitOfWork — one transaction boundary for the finance bounded context.

Guarantees atomicity between: financial document, journal entry, obligation and
outbox event. Repositories never commit; the UoW owns the boundary.
"""

from __future__ import annotations

from typing import Any

from backend.infrastructure.db.repositories.finance.account_repository import AccountRepository
from backend.infrastructure.db.repositories.finance.budget_repository import BudgetRepository
from backend.infrastructure.db.repositories.finance.collection_repository import CollectionRepository
from backend.infrastructure.db.repositories.finance.commercial_obligation_repository import (
    CommercialObligationRepository,
)
from backend.infrastructure.db.repositories.finance.financial_document_repository import (
    FinancialDocumentRepository,
)
from backend.infrastructure.db.repositories.finance.fiscal_period_repository import (
    FiscalPeriodRepository,
)
from backend.infrastructure.db.repositories.finance.fixed_asset_repository import (
    FixedAssetRepository,
)
from backend.infrastructure.db.repositories.finance.journal_entry_repository import (
    JournalEntryRepository,
)
from backend.infrastructure.db.repositories.finance.journal_repository import JournalRepository
from backend.infrastructure.db.repositories.finance.outbox_repository import OutboxRepository
from backend.infrastructure.db.repositories.finance.payable_repository import PayableRepository
from backend.infrastructure.db.repositories.finance.posting_profile_repository import (
    PostingProfileRepository,
)
from backend.infrastructure.db.repositories.finance.processed_event_repository import (
    ProcessedEventRepository,
)
from backend.infrastructure.db.repositories.finance.receivable_repository import (
    ReceivableRepository,
)
from backend.infrastructure.db.repositories.finance.reconciliation_repository import (
    ReconciliationRepository,
)
from backend.infrastructure.db.repositories.finance.supplier_payment_repository import (
    SupplierPaymentRepository,
)
from backend.infrastructure.db.repositories.finance.treasury_repository import TreasuryRepository


class FinanceUnitOfWork:
    """Context manager: commits on clean exit, rolls back on exception."""

    def __init__(self, connection: Any) -> None:
        self.connection = connection
        self.accounts = AccountRepository(connection)
        self.journals = JournalRepository(connection)
        self.journal_entries = JournalEntryRepository(connection)
        self.fiscal_periods = FiscalPeriodRepository(connection)
        self.financial_documents = FinancialDocumentRepository(connection)
        self.receivables = ReceivableRepository(connection)
        self.collections = CollectionRepository(connection)
        self.payables = PayableRepository(connection)
        self.supplier_payments = SupplierPaymentRepository(connection)
        self.treasury = TreasuryRepository(connection)
        self.reconciliations = ReconciliationRepository(connection)
        self.budgets = BudgetRepository(connection)
        self.fixed_assets = FixedAssetRepository(connection)
        self.posting_profiles = PostingProfileRepository(connection)
        self.commercial_obligations = CommercialObligationRepository(connection)
        self.processed_events = ProcessedEventRepository(connection)
        self.outbox = OutboxRepository(connection)
        self._completed = False

    def __enter__(self) -> "FinanceUnitOfWork":
        self._completed = False
        return self

    def __exit__(self, exc_type, exc, traceback) -> bool:
        if exc_type is not None:
            self.rollback()
        elif not self._completed:
            self.commit()
        return False

    def commit(self) -> None:
        self.connection.commit()
        self._completed = True

    def rollback(self) -> None:
        rollback = getattr(self.connection, "rollback", None)
        if rollback is not None:
            rollback()
        self._completed = True
