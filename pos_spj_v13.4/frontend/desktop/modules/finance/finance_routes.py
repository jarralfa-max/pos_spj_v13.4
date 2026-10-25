"""Composition root for the finance desktop module.

This is the ONLY place that touches the database connection to wire query
services, use cases and the adapters to other contexts. The view and pages
never see the connection nor the AppContainer.
"""

from __future__ import annotations

from backend.application.finance.authorization import (
    FinanceAuthorizationPolicy,
    FinanceSessionPermissionChecker,
)
from backend.application.finance.finance_commands import FinanceCommandService
from backend.application.queries.finance.account_query_service import AccountQueryService
from backend.application.queries.finance.budget_query_service import BudgetQueryService
from backend.application.queries.finance.cash_projection_query_service import (
    CashProjectionQueryService,
)
from backend.application.queries.finance.commercial_obligation_query_service import (
    CommercialObligationQueryService,
)
from backend.application.queries.finance.finance_audit_query_service import (
    FinanceAuditQueryService,
)
from backend.application.queries.finance.finance_dashboard_query_service import (
    FinanceDashboardQueryService,
)
from backend.application.queries.finance.finance_settings_query_service import (
    FinanceSettingsQueryService,
)
from backend.application.queries.finance.financial_statement_query_service import (
    FinancialStatementQueryService,
)
from backend.application.queries.finance.fiscal_period_query_service import (
    FiscalPeriodQueryService,
)
from backend.application.queries.finance.fixed_asset_query_service import (
    FixedAssetQueryService,
)
from backend.application.queries.finance.general_ledger_query_service import (
    GeneralLedgerQueryService,
)
from backend.application.queries.finance.journal_query_service import JournalQueryService
from backend.application.queries.finance.payable_query_service import PayableQueryService
from backend.application.queries.finance.profitability_query_service import (
    ProfitabilityQueryService,
)
from backend.application.queries.finance.receivable_query_service import ReceivableQueryService
from backend.application.queries.finance.reconciliation_query_service import (
    ReconciliationQueryService,
)
from backend.application.queries.finance.treasury_query_service import TreasuryQueryService
from backend.application.queries.finance.trial_balance_query_service import (
    TrialBalanceQueryService,
)
from backend.application.services.finance.finance_bootstrap import bootstrap_finance
from backend.application.use_cases.finance.accrue_expense_use_case import (
    AccrueExpenseUseCase,
    CancelExpenseUseCase,
)
from backend.application.use_cases.finance.apply_collection_use_case import (
    ApplyCollectionUseCase,
)
from backend.application.use_cases.finance.approve_budget_use_case import BudgetWorkflowUseCase
from backend.application.use_cases.finance.approve_expense_use_case import ApproveExpenseUseCase
from backend.application.use_cases.finance.authorize_close_exception_use_case import (
    AuthorizeCloseExceptionUseCase,
)
from backend.application.use_cases.finance.authorize_supplier_payment_use_case import (
    AuthorizeSupplierPaymentUseCase,
)
from backend.application.use_cases.finance.capitalize_asset_use_case import (
    CapitalizeAssetUseCase,
)
from backend.application.use_cases.finance.close_fiscal_period_use_case import (
    CloseFiscalPeriodUseCase,
)
from backend.application.use_cases.finance.create_account_use_case import CreateAccountUseCase
from backend.application.use_cases.finance.create_budget_use_case import (
    CreateBudgetUseCase,
    CreateBudgetVersionUseCase,
)
from backend.application.use_cases.finance.create_journal_entry_use_case import (
    CancelJournalEntryUseCase,
    CreateJournalEntryUseCase,
    UpdateJournalEntryDraftUseCase,
)
from backend.application.use_cases.finance.create_payable_use_case import CreatePayableUseCase
from backend.application.use_cases.finance.create_receivable_use_case import (
    CreateReceivableUseCase,
)
from backend.application.use_cases.finance.dispose_asset_use_case import (
    ChangeAssetStatusUseCase,
    DisposeAssetUseCase,
)
from backend.application.use_cases.finance.execute_supplier_payment_use_case import (
    ExecuteSupplierPaymentUseCase,
)
from backend.application.use_cases.finance.finance_configuration_use_cases import (
    ManageCurrencyUseCase,
    ManageDimensionsUseCase,
    ManageTaxConfigurationUseCase,
    UpdateFinanceSettingsUseCase,
    UpdatePostingProfileUseCase,
)
from backend.application.use_cases.finance.import_bank_statement_use_case import (
    ImportBankStatementUseCase,
)
from backend.application.use_cases.finance.manage_expense_rules_use_case import (
    ManageExpenseRulesUseCase,
)
from backend.application.use_cases.finance.manage_payable_controls_use_case import (
    ManagePayableControlsUseCase,
)
from backend.application.use_cases.finance.manage_receivable_followup_use_case import (
    DisputeReceivableUseCase,
    RegisterPaymentPromiseUseCase,
)
from backend.application.use_cases.finance.manage_treasury_account_use_case import (
    ManageTreasuryAccountUseCase,
)
from backend.application.use_cases.finance.mark_overdue_documents_use_case import (
    MarkOverdueDocumentsUseCase,
)
from backend.application.use_cases.finance.open_fiscal_period_use_case import (
    OpenFiscalPeriodUseCase,
)
from backend.application.use_cases.finance.post_journal_entry_use_case import (
    PostJournalEntryUseCase,
)
from backend.application.use_cases.finance.reconcile_bank_statement_use_case import (
    ReconcileBankStatementUseCase,
)
from backend.application.use_cases.finance.record_export_use_case import (
    RecordFinanceExportUseCase,
)
from backend.application.use_cases.finance.register_capital_movement_use_case import (
    RegisterCapitalMovementUseCase,
)
from backend.application.use_cases.finance.register_collection_use_case import (
    RegisterCollectionUseCase,
)
from backend.application.use_cases.finance.register_expense_request_use_case import (
    RegisterExpenseRequestUseCase,
)
from backend.application.use_cases.finance.register_reconciliation_adjustment_use_case import (
    RegisterReconciliationAdjustmentUseCase,
)
from backend.application.use_cases.finance.register_treasury_movement_use_case import (
    RegisterTreasuryMovementUseCase,
)
from backend.application.use_cases.finance.register_treasury_transfer_use_case import (
    RegisterTreasuryTransferUseCase,
)
from backend.application.use_cases.finance.reopen_fiscal_period_use_case import (
    ReopenFiscalPeriodUseCase,
)
from backend.application.use_cases.finance.reverse_journal_entry_use_case import (
    ReverseJournalEntryUseCase,
)
from backend.application.use_cases.finance.run_depreciation_use_case import (
    RunDepreciationUseCase,
)
from backend.application.use_cases.finance.schedule_supplier_payment_use_case import (
    ScheduleSupplierPaymentUseCase,
)
from backend.application.use_cases.finance.supplier_advance_use_cases import (
    ApplySupplierAdvanceUseCase,
    RegisterSupplierAdvanceUseCase,
)
from backend.application.use_cases.finance.update_account_use_case import UpdateAccountUseCase
from backend.application.use_cases.finance.validate_journal_entry_use_case import (
    ValidateJournalEntryUseCase,
)
from backend.application.use_cases.finance.write_off_receivable_use_case import (
    WriteOffReceivableUseCase,
)
from backend.infrastructure.finance.bank_statement_reader import (
    parse_manual_lines,
    read_statement_file,
)
from backend.infrastructure.integrations.finance_close_sources import (
    SqliteOperationalCloseSources,
)
from backend.infrastructure.integrations.finance_party_directories import (
    SqliteCustomerDirectory,
    SqliteProductDirectory,
    SqliteSupplierNameDirectory,
)
from backend.infrastructure.integrations.finance_supplier_directory import (
    SqliteSupplierDirectory,
)
from frontend.desktop.modules.finance.finance_presenter import FinancePresenter


def build_query_services(connection) -> dict:
    customers = SqliteCustomerDirectory(connection)
    suppliers = SqliteSupplierNameDirectory(connection)
    products = SqliteProductDirectory(connection)
    return {
        "dashboard": FinanceDashboardQueryService(connection, products=products),
        "accounts": AccountQueryService(connection),
        "journal": JournalQueryService(connection),
        "periods": FiscalPeriodQueryService(connection),
        "ledger": GeneralLedgerQueryService(connection),
        "trial_balance": TrialBalanceQueryService(connection),
        "statements": FinancialStatementQueryService(connection),
        "receivables": ReceivableQueryService(connection, customers),
        "payables": PayableQueryService(connection, suppliers),
        "treasury": TreasuryQueryService(connection),
        "reconciliation": ReconciliationQueryService(connection),
        "budgets": BudgetQueryService(connection),
        "assets": FixedAssetQueryService(connection),
        "obligations": CommercialObligationQueryService(connection),
        "profitability": ProfitabilityQueryService(connection, products=products,
                                                   customers=customers),
        "projection": CashProjectionQueryService(connection),
        "audit": FinanceAuditQueryService(connection),
        "settings": FinanceSettingsQueryService(connection),
    }


def build_use_cases(connection) -> dict:
    supplier_directory = SqliteSupplierDirectory(connection)
    return {
        "create_account": CreateAccountUseCase(),
        "update_account": UpdateAccountUseCase(),
        "create_journal_entry": CreateJournalEntryUseCase(),
        "update_journal_entry": UpdateJournalEntryDraftUseCase(),
        "cancel_journal_entry": CancelJournalEntryUseCase(),
        "validate_journal_entry": ValidateJournalEntryUseCase(),
        "post_journal_entry": PostJournalEntryUseCase(),
        "reverse_entry": ReverseJournalEntryUseCase(),
        "open_period": OpenFiscalPeriodUseCase(),
        "close_period": CloseFiscalPeriodUseCase(SqliteOperationalCloseSources(connection)),
        "reopen_period": ReopenFiscalPeriodUseCase(),
        "authorize_close_exception": AuthorizeCloseExceptionUseCase(),
        "create_receivable": CreateReceivableUseCase(),
        "register_collection": RegisterCollectionUseCase(),
        "apply_collection": ApplyCollectionUseCase(),
        "write_off_receivable": WriteOffReceivableUseCase(),
        "receivable_followup": DisputeReceivableUseCase(),
        "payment_promise": RegisterPaymentPromiseUseCase(),
        "mark_overdue": MarkOverdueDocumentsUseCase(),
        "create_payable": CreatePayableUseCase(),
        "schedule_payment": ScheduleSupplierPaymentUseCase(supplier_directory),
        "authorize_payment": AuthorizeSupplierPaymentUseCase(),
        "execute_payment": ExecuteSupplierPaymentUseCase(supplier_directory),
        "payable_controls": ManagePayableControlsUseCase(),
        "supplier_advance": RegisterSupplierAdvanceUseCase(supplier_directory),
        "apply_supplier_advance": ApplySupplierAdvanceUseCase(),
        "treasury_transfer": RegisterTreasuryTransferUseCase(),
        "treasury_movement": RegisterTreasuryMovementUseCase(),
        "treasury_account": ManageTreasuryAccountUseCase(),
        "capital_movement": RegisterCapitalMovementUseCase(),
        "import_statement": ImportBankStatementUseCase(),
        "reconcile": ReconcileBankStatementUseCase(),
        "reconciliation_adjustment": RegisterReconciliationAdjustmentUseCase(),
        "create_budget": CreateBudgetUseCase(),
        "create_budget_version": CreateBudgetVersionUseCase(),
        "budget_workflow": BudgetWorkflowUseCase(),
        "expense_request": RegisterExpenseRequestUseCase(),
        "approve_expense": ApproveExpenseUseCase(),
        "accrue_expense": AccrueExpenseUseCase(),
        "cancel_expense": CancelExpenseUseCase(),
        "expense_rules": ManageExpenseRulesUseCase(),
        "capitalize_asset": CapitalizeAssetUseCase(),
        "run_depreciation": RunDepreciationUseCase(),
        "dispose_asset": DisposeAssetUseCase(),
        "asset_status": ChangeAssetStatusUseCase(),
        "update_settings": UpdateFinanceSettingsUseCase(),
        "update_posting_profile": UpdatePostingProfileUseCase(),
        "dimensions": ManageDimensionsUseCase(),
        "taxes": ManageTaxConfigurationUseCase(),
        "currencies": ManageCurrencyUseCase(),
        "audit_export": RecordFinanceExportUseCase(),
    }


def build_finance_presenter(connection, session_context=None) -> FinancePresenter:
    """Compone el módulo. Los comandos pasan por ``FinanceCommandService`` con
    la política de permisos sobre la sesión viva: sin sesión, o con una de
    sólo lectura, todo comando se rechaza."""
    bootstrap_finance(connection)
    commands = FinanceCommandService(
        connection_provider=lambda: connection,
        use_cases=build_use_cases(connection),
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

    def _credit_summary(customer_id: str):
        # Exposición de crédito que publica el contexto de Clientes (CRM-21).
        from backend.application.customer_credit.queries.customer_accounts_receivable_summary_query import (
            CustomerAccountsReceivableSummaryQuery,
        )
        return CustomerAccountsReceivableSummaryQuery(connection).get_summary(customer_id)

    return FinancePresenter(
        query_services=build_query_services(connection),
        commands=commands,
        statement_reader=read_statement_file,
        manual_statement_parser=parse_manual_lines,
        crm_summary=_credit_summary,
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
