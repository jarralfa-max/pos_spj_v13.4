"""Composition root for the finance desktop module.

This is the ONLY place that touches the database connection to wire query
services and use cases. The view and pages never see the connection nor the
AppContainer.
"""

from __future__ import annotations

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
from backend.application.finance.authorization import (
    FinanceAuthorizationPolicy,
    FinanceSessionPermissionChecker,
)
from backend.application.finance.finance_commands import FinanceCommandService
from backend.application.services.finance.finance_bootstrap import bootstrap_finance
from backend.application.use_cases.finance.budget_use_cases import (
    ApproveBudgetUseCase,
    CreateBudgetUseCase,
    RegisterExpenseRequestUseCase,
    ResolveExpenseRequestUseCase,
    SubmitBudgetUseCase,
)
from backend.application.use_cases.finance.capital_and_asset_use_cases import (
    CapitalizeAssetUseCase,
    RegisterCapitalContributionUseCase,
    RunDepreciationUseCase,
)
from backend.application.use_cases.finance.fiscal_period_use_cases import (
    AuthorizeCloseExceptionUseCase,
    CloseFiscalPeriodUseCase,
    ReopenFiscalPeriodUseCase,
)
from backend.application.use_cases.finance.journal_use_cases import ReverseJournalEntryUseCase
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
    ImportBankStatementUseCase,
    RegisterTreasuryTransferUseCase,
)
from frontend.desktop.modules.finance.finance_presenter import FinancePresenter


def build_finance_presenter(connection, session_context=None) -> FinancePresenter:
    """Compone el módulo. Los comandos pasan por ``FinanceCommandService`` con
    la política de permisos sobre la sesión viva (auditoría F02): sin sesión,
    o con una de sólo lectura, todo comando se rechaza."""
    bootstrap_finance(connection)

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
    query_services["customer_names"] = query_services["receivables"].customer_display_names
    use_cases = {
        "register_collection": RegisterCollectionUseCase(),
        "schedule_payment": ScheduleSupplierPaymentUseCase(),
        "authorize_payment": AuthorizeSupplierPaymentUseCase(),
        "execute_payment": ExecuteSupplierPaymentUseCase(),
        "treasury_transfer": RegisterTreasuryTransferUseCase(),
        "import_statement": ImportBankStatementUseCase(),
        "reconcile": ReconcileBankStatementUseCase(),
        "create_budget": CreateBudgetUseCase(),
        "submit_budget": SubmitBudgetUseCase(),
        "approve_budget": ApproveBudgetUseCase(),
        "expense_request": RegisterExpenseRequestUseCase(),
        "resolve_expense": ResolveExpenseRequestUseCase(),
        "capital_contribution": RegisterCapitalContributionUseCase(),
        "capitalize_asset": CapitalizeAssetUseCase(),
        "run_depreciation": RunDepreciationUseCase(),
        "close_period": CloseFiscalPeriodUseCase(),
        "reopen_period": ReopenFiscalPeriodUseCase(),
        "authorize_close_exception": AuthorizeCloseExceptionUseCase(),
        "reverse_entry": ReverseJournalEntryUseCase(),
    }
    commands = FinanceCommandService(
        connection_provider=lambda: connection,
        use_cases=use_cases,
        authorization=FinanceAuthorizationPolicy(
            FinanceSessionPermissionChecker(session_context)),
        actor_provider=lambda: getattr(session_context, "user_id", None),
        after_command=lambda: _dispatch_finance_outbox(connection),
    )

    def _suppliers():
        from frontend.desktop.modules.finance.suppliers.supplier_routes import (
            build_supplier_presenter,
        )
        return build_supplier_presenter(connection, session_context)

    return FinancePresenter(
        connection_provider=lambda: connection,
        query_services=query_services,
        use_cases={},
        session_context=session_context,
        commands=commands,
        embedded_presenters={"suppliers": _suppliers},
    )


def _dispatch_finance_outbox(connection) -> dict:
    from backend.application.services.finance.outbox_dispatcher import dispatch_finance_outbox
    from backend.shared.events.application_bus import get_bus
    return dispatch_finance_outbox(connection, get_bus())


def create_finance_view(container, parent=None):
    """Factory used by navigation. Extracts only what the module needs."""
    from frontend.desktop.modules.finance.finance_view import FinanceView

    connection = getattr(container, "db", None) or getattr(container, "db_conn", None)
    session_context = getattr(container, "session_context", None)
    presenter = build_finance_presenter(connection, session_context)
    return FinanceView(presenter, parent)
