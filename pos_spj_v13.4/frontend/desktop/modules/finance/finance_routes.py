"""Composition root for the finance desktop module.

This is the ONLY place that touches the database connection to wire query
services and use cases. The view and pages never see the connection nor the
AppContainer.
"""

from __future__ import annotations

from datetime import date

from backend.application.queries.finance.finance_read_services import (
    AccountQueryService,
    BudgetQueryService,
    CommercialObligationQueryService,
    FinanceDashboardQueryService,
    FixedAssetQueryService,
    JournalQueryService,
    PayableQueryService,
    ReceivableQueryService,
    ReconciliationQueryService,
    TreasuryQueryService,
)
from backend.application.queries.finance.financial_statement_query_service import (
    FinancialStatementQueryService,
)
from backend.application.queries.finance.general_ledger_query_service import (
    GeneralLedgerQueryService,
)
from backend.application.services.finance.finance_bootstrap import bootstrap_finance
from backend.application.services.finance.posting_engine import PostingEngine
from backend.application.use_cases.finance.budget_use_cases import (
    ApproveBudgetUseCase,
    CreateBudgetUseCase,
    RegisterExpenseRequestUseCase,
    SubmitBudgetUseCase,
)
from backend.application.use_cases.finance.capital_and_asset_use_cases import (
    CapitalizeAssetUseCase,
    RegisterCapitalContributionUseCase,
    RunDepreciationUseCase,
)
from backend.application.use_cases.finance.fiscal_period_use_cases import (
    CloseFiscalPeriodUseCase,
    ReopenFiscalPeriodUseCase,
)
from backend.application.use_cases.finance.payable_use_cases import (
    AuthorizeSupplierPaymentUseCase,
    ExecuteSupplierPaymentUseCase,
    ScheduleSupplierPaymentUseCase,
)
from backend.application.use_cases.finance.receivable_use_cases import (
    RegisterCollectionUseCase,
)
from backend.application.use_cases.finance.reconcile_bank_statement_use_case import (
    ReconcileBankStatementUseCase,
)
from backend.application.use_cases.finance.treasury_use_cases import (
    RegisterTreasuryTransferUseCase,
)
from backend.infrastructure.db.repositories.finance.unit_of_work import FinanceUnitOfWork
from backend.shared.ids import new_uuid
from frontend.desktop.modules.finance.finance_presenter import FinancePresenter


def build_finance_presenter(connection, session_context=None) -> FinancePresenter:
    bootstrap_finance(connection)

    def _reverse_entry(journal_entry_id: str, reason: str) -> None:
        engine = PostingEngine()
        with FinanceUnitOfWork(connection) as uow:
            entry = uow.journal_entries.get(journal_entry_id)
            if entry is None:
                from backend.domain.finance.exceptions import FinanceDomainError
                raise FinanceDomainError("El asiento no existe")
            engine.reverse(uow, entry, date.today(), reason, new_uuid())

    query_services = {
        "dashboard": FinanceDashboardQueryService(connection),
        "accounts": AccountQueryService(connection),
        "journal": JournalQueryService(connection),
        "ledger": GeneralLedgerQueryService(connection),
        "statements": FinancialStatementQueryService(connection),
        "receivables": ReceivableQueryService(connection),
        "payables": PayableQueryService(connection),
        "treasury": TreasuryQueryService(connection),
        "reconciliation": ReconciliationQueryService(connection),
        "budgets": BudgetQueryService(connection),
        "assets": FixedAssetQueryService(connection),
        "obligations": CommercialObligationQueryService(connection),
    }
    use_cases = {
        "register_collection": RegisterCollectionUseCase(),
        "schedule_payment": ScheduleSupplierPaymentUseCase(),
        "authorize_payment": AuthorizeSupplierPaymentUseCase(),
        "execute_payment": ExecuteSupplierPaymentUseCase(),
        "treasury_transfer": RegisterTreasuryTransferUseCase(),
        "reconcile": ReconcileBankStatementUseCase(),
        "create_budget": CreateBudgetUseCase(),
        "submit_budget": SubmitBudgetUseCase(),
        "approve_budget": ApproveBudgetUseCase(),
        "expense_request": RegisterExpenseRequestUseCase(),
        "capital_contribution": RegisterCapitalContributionUseCase(),
        "capitalize_asset": CapitalizeAssetUseCase(),
        "run_depreciation": RunDepreciationUseCase(),
        "close_period": CloseFiscalPeriodUseCase(),
        "reopen_period": ReopenFiscalPeriodUseCase(),
        "reverse_entry": _reverse_entry,
    }
    return FinancePresenter(
        connection_provider=lambda: connection,
        query_services=query_services,
        use_cases=use_cases,
        session_context=session_context,
    )


def create_finance_view(container, parent=None):
    """Factory used by navigation. Extracts only what the module needs."""
    from frontend.desktop.modules.finance.finance_view import FinanceView

    connection = getattr(container, "db", None) or getattr(container, "db_conn", None)
    session_context = getattr(container, "session_context", None)
    presenter = build_finance_presenter(connection, session_context)
    return FinanceView(presenter, parent)
