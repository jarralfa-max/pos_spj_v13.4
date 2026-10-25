"""FinanceUnitOfWork — one transaction boundary for the finance bounded context.

Guarantees atomicity between: financial document, journal entry, obligation,
audit record and outbox event. Repositories never commit; the UoW owns the boundary.
"""

from __future__ import annotations

from typing import Any

from backend.domain.finance.entities.audit_record import AuditRecord
from backend.domain.finance.entities.finance_settings import FinanceSettings
from backend.domain.finance.enums import AuditAction
from backend.infrastructure.db.repositories.finance.account_repository import AccountRepository
from backend.infrastructure.db.repositories.finance.analytics_repositories import (
    CashPlanningRepository,
    ProfitabilityFactRepository,
)
from backend.infrastructure.db.repositories.finance.audit_log_repository import (
    FinanceAuditLogRepository,
)
from backend.infrastructure.db.repositories.finance.audit_support_repositories import (
    CloseExceptionRepository,
    ExpenseRequestRepository,
    ReceivableChargeRepository,
)
from backend.infrastructure.db.repositories.finance.budget_repository import BudgetRepository
from backend.infrastructure.db.repositories.finance.capital_repository import CapitalRepository
from backend.infrastructure.db.repositories.finance.collection_repository import CollectionRepository
from backend.infrastructure.db.repositories.finance.commercial_obligation_repository import (
    CommercialObligationRepository,
)
from backend.infrastructure.db.repositories.finance.cost_center_repository import (
    CostCenterRepository,
)
from backend.infrastructure.db.repositories.finance.currency_repository import CurrencyRepository
from backend.infrastructure.db.repositories.finance.dimension_repository import (
    DimensionRepository,
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
from backend.infrastructure.db.repositories.finance.profit_center_repository import (
    ProfitCenterRepository,
)
from backend.infrastructure.db.repositories.finance.receivable_repository import (
    ReceivableRepository,
)
from backend.infrastructure.db.repositories.finance.reconciliation_repository import (
    ReconciliationRepository,
)
from backend.infrastructure.db.repositories.finance.settings_repository import (
    FinanceSettingsRepository,
)
from backend.infrastructure.db.repositories.finance.supplier_payment_repository import (
    SupplierPaymentRepository,
)
from backend.infrastructure.db.repositories.finance.tax_repository import TaxRepository
from backend.infrastructure.db.repositories.finance.treasury_repository import TreasuryRepository
from backend.infrastructure.db.transaction import TransactionalUnitOfWork


class FinanceUnitOfWork(TransactionalUnitOfWork):
    """Context manager: commits on clean exit, rolls back on exception.

    ``owns_transaction=False`` (auditoría CRM F01, 2026-10-09): la unidad de
    trabajo participa en una transacción que abrió OTRO flujo (p. ej. el cobro a
    crédito de una venta) y no confirma ni revierte la conexión — lo decide ese
    flujo. Mismo contrato que ``InventoryUnitOfWork`` y ``SalesUnitOfWork``."""

    def __init__(self, connection: Any, *, owns_transaction: bool = True) -> None:
        self.connection = connection
        self._owns_transaction = owns_transaction
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
        self.receivable_charges = ReceivableChargeRepository(connection)
        self.expense_requests = ExpenseRequestRepository(connection)
        self.close_exceptions = CloseExceptionRepository(connection)
        self.cost_centers = CostCenterRepository(connection)
        self.profit_centers = ProfitCenterRepository(connection)
        self.dimensions = DimensionRepository(connection)
        self.currencies = CurrencyRepository(connection)
        self.taxes = TaxRepository(connection)
        self.capital = CapitalRepository(connection)
        self.profitability = ProfitabilityFactRepository(connection)
        self.cash_planning = CashPlanningRepository(connection)
        self.settings_store = FinanceSettingsRepository(connection)
        self.audit_log = FinanceAuditLogRepository(connection)
        self._settings: FinanceSettings | None = None
        self._completed = False

    # ── configuración y auditoría dentro de la misma transacción ──────────
    @property
    def settings(self) -> FinanceSettings:
        if self._settings is None:
            self._settings = self.settings_store.load()
        return self._settings

    def audit(self, action: AuditAction, *, entity_type: str, entity_id: str,
              operation_id: str, user_id: str | None, before: dict | None = None,
              after: dict | None = None, reason: str | None = None,
              branch_id: str | None = None) -> None:
        self.audit_log.append(AuditRecord.create(
            action=action, entity_type=entity_type, entity_id=entity_id,
            operation_id=operation_id, user_id=user_id, before=before, after=after,
            reason=reason, branch_id=branch_id))

    # ── frontera transaccional ────────────────────────────────────────────
