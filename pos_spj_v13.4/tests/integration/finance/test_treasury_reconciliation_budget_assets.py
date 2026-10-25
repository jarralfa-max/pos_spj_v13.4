"""FASES 9-13 — tesorería, conciliación, presupuestos, capital y activos."""

from datetime import date

import pytest

from backend.application.services.finance.posting_engine import PostingEngine
from backend.application.use_cases.finance.approve_budget_use_case import BudgetWorkflowUseCase
from backend.application.use_cases.finance.approve_expense_use_case import ApproveExpenseUseCase
from backend.application.use_cases.finance.capitalize_asset_use_case import CapitalizeAssetUseCase
from backend.application.use_cases.finance.create_budget_use_case import CreateBudgetUseCase
from backend.application.use_cases.finance.import_bank_statement_use_case import (
    ImportBankStatementUseCase,
)
from backend.application.use_cases.finance.reconcile_bank_statement_use_case import (
    ReconcileBankStatementUseCase,
)
from backend.application.use_cases.finance.register_capital_movement_use_case import (
    RegisterCapitalMovementUseCase,
)
from backend.application.use_cases.finance.register_expense_request_use_case import (
    RegisterExpenseRequestUseCase,
)
from backend.application.use_cases.finance.register_treasury_transfer_use_case import (
    RegisterTreasuryTransferUseCase,
)
from backend.application.use_cases.finance.run_depreciation_use_case import RunDepreciationUseCase
from backend.domain.finance.enums import (
    CapitalMovementKind,
    FixedAssetStatus,
    JournalType,
    PostingPurpose,
    ReconciliationStatus,
    TreasuryAccountType,
)
from backend.domain.finance.exceptions import (
    BudgetControlError,
    FinanceDomainError,
    InsufficientTreasuryFundsError,
    ReconciliationError,
)
from backend.domain.finance.services.journal_posting_service import LineSpec
from backend.domain.finance.value_objects.money import Money
from backend.domain.finance.value_objects.posting_reference import PostingReference
from backend.infrastructure.db.repositories.finance.unit_of_work import FinanceUnitOfWork
from backend.shared.ids import new_uuid
from tests.integration.finance.conftest import approved_budget, fund

TODAY = date(2026, 7, 16)


def _accounts_by_type(conn):
    with FinanceUnitOfWork(conn) as uow:
        return {a.account_type: a for a in uow.treasury.list_active()}


class TestTreasury:
    def test_transfer_between_accounts(self, bootstrapped_conn):
        accounts = _accounts_by_type(bootstrapped_conn)
        cash = accounts[TreasuryAccountType.GENERAL_CASH]
        bank = accounts[TreasuryAccountType.BANK]
        fund(bootstrapped_conn, cash.id, "5000.00")
        entry_id = RegisterTreasuryTransferUseCase().execute(
            bootstrapped_conn, source_treasury_account_id=cash.id,
            target_treasury_account_id=bank.id, amount="5000.00",
            transfer_date=TODAY, operation_id=new_uuid())
        with FinanceUnitOfWork(bootstrapped_conn) as uow:
            entry = uow.journal_entries.get(entry_id)
        assert entry.is_balanced()
        assert entry.total_debits().to_string() == "5000.00"
        assert {l.account_id for l in entry.lines} == {cash.ledger_account_id,
                                                       bank.ledger_account_id}

    def test_transfer_to_same_account_rejected(self, bootstrapped_conn):
        bank = _accounts_by_type(bootstrapped_conn)[TreasuryAccountType.BANK]
        with pytest.raises(FinanceDomainError):
            RegisterTreasuryTransferUseCase().execute(
                bootstrapped_conn, source_treasury_account_id=bank.id,
                target_treasury_account_id=bank.id, amount="1.00",
                transfer_date=TODAY, operation_id=new_uuid())

    def test_transfer_without_funds_rejected(self, bootstrapped_conn):
        accounts = _accounts_by_type(bootstrapped_conn)
        with pytest.raises(InsufficientTreasuryFundsError):
            RegisterTreasuryTransferUseCase().execute(
                bootstrapped_conn,
                source_treasury_account_id=accounts[TreasuryAccountType.GENERAL_CASH].id,
                target_treasury_account_id=accounts[TreasuryAccountType.BANK].id,
                amount="1.00", transfer_date=TODAY, operation_id=new_uuid())

    def test_transfer_idempotent(self, bootstrapped_conn):
        accounts = _accounts_by_type(bootstrapped_conn)
        fund(bootstrapped_conn, accounts[TreasuryAccountType.GENERAL_CASH].id, "100.00")
        op = new_uuid()
        uc = RegisterTreasuryTransferUseCase()
        kwargs = dict(
            source_treasury_account_id=accounts[TreasuryAccountType.GENERAL_CASH].id,
            target_treasury_account_id=accounts[TreasuryAccountType.BANK].id,
            amount="100.00", transfer_date=TODAY, operation_id=op)
        assert uc.execute(bootstrapped_conn, **kwargs) == uc.execute(bootstrapped_conn, **kwargs)


class TestReconciliation:
    def _bank_inflow(self, conn, amount="1500.00"):
        """Post a bank inflow so a ledger line exists to match."""
        bank = _accounts_by_type(conn)[TreasuryAccountType.BANK]
        with FinanceUnitOfWork(conn) as uow:
            capital = uow.posting_profiles.find_effective("CAPITAL", TODAY)
            entry = PostingEngine().post(
                uow, JournalType.BANK, TODAY, "Depósito",
                PostingReference("finance", new_uuid(), PostingPurpose.MANUAL, new_uuid()),
                [LineSpec(bank.ledger_account_id, debit=Money.from_string(amount)),
                 LineSpec(capital.account_for("capital_account_id"),
                          credit=Money.from_string(amount))])
        return bank, next(l for l in entry.lines if l.debit.is_positive())

    def _statement(self, conn, bank, amount, closing=None):
        return ImportBankStatementUseCase().execute(
            conn, treasury_account_id=bank.id, statement_date=TODAY,
            opening_balance="0.00", closing_balance=closing or amount,
            lines=[{"transaction_date": "2026-07-16", "description": "DEP",
                    "amount": amount}], operation_id=new_uuid(), imported_by="ana")

    def test_import_match_complete_and_revert(self, bootstrapped_conn):
        bank, ledger_line = self._bank_inflow(bootstrapped_conn)
        statement = self._statement(bootstrapped_conn, bank, "1500.00")
        uc = ReconcileBankStatementUseCase()
        reconciliation = uc.start(bootstrapped_conn, bank_statement_id=statement.id,
                                  operation_id=new_uuid())
        assert uc.match(bootstrapped_conn, reconciliation_id=reconciliation.id,
                        bank_statement_line_id=statement.lines[0].id,
                        journal_line_id=ledger_line.id, matched_by="ana") is True
        uc.complete(bootstrapped_conn, reconciliation_id=reconciliation.id, completed_by="ana")
        with FinanceUnitOfWork(bootstrapped_conn) as uow:
            assert uow.reconciliations.get(reconciliation.id).status \
                is ReconciliationStatus.COMPLETED
        with pytest.raises(ReconciliationError):
            uc.revert(bootstrapped_conn, reconciliation_id=reconciliation.id,
                      reverted_by="beto", reason="")
        uc.revert(bootstrapped_conn, reconciliation_id=reconciliation.id,
                  reverted_by="beto", reason="error de captura")
        with FinanceUnitOfWork(bootstrapped_conn) as uow:
            assert uow.reconciliations.get(reconciliation.id).status \
                is ReconciliationStatus.REVERTED

    def test_amount_mismatch_cannot_match(self, bootstrapped_conn):
        bank, ledger_line = self._bank_inflow(bootstrapped_conn, amount="1500.00")
        statement = self._statement(bootstrapped_conn, bank, "999.00")
        uc = ReconcileBankStatementUseCase()
        reconciliation = uc.start(bootstrapped_conn, bank_statement_id=statement.id,
                                  operation_id=new_uuid())
        with pytest.raises(ReconciliationError):
            uc.match(bootstrapped_conn, reconciliation_id=reconciliation.id,
                     bank_statement_line_id=statement.lines[0].id,
                     journal_line_id=ledger_line.id, matched_by="ana")

    def test_inconsistent_statement_rejected(self, bootstrapped_conn):
        bank, _ = self._bank_inflow(bootstrapped_conn)
        with pytest.raises(ReconciliationError):
            self._statement(bootstrapped_conn, bank, "50.00", closing="100.00")


class TestBudgets:
    def test_commitment_happens_on_approval(self, bootstrapped_conn):
        budget = approved_budget(bootstrapped_conn)
        with FinanceUnitOfWork(bootstrapped_conn) as uow:
            account = uow.accounts.get_by_code("6130")
        request_id = RegisterExpenseRequestUseCase().execute(
            bootstrapped_conn, account_id=account.id, amount="4000.00",
            request_date=TODAY, operation_id=new_uuid(), requested_by="carla")
        with FinanceUnitOfWork(bootstrapped_conn) as uow:
            assert uow.budgets.get(budget.id).lines[0].committed_amount.is_zero()
        ApproveExpenseUseCase().approve(bootstrapped_conn, expense_request_id=request_id,
                                        approver_id="dani", operation_id=new_uuid())
        with FinanceUnitOfWork(bootstrapped_conn) as uow:
            stored = uow.budgets.get(budget.id)
        assert stored.lines[0].committed_amount.to_string() == "4000.00"
        assert stored.lines[0].available().to_string() == "6000.00"

    def test_blocking_control_and_exceeded_event(self, bootstrapped_conn):
        budget = approved_budget(bootstrapped_conn, planned="1000.00")
        with FinanceUnitOfWork(bootstrapped_conn) as uow:
            account = uow.accounts.get_by_code("6130")
        with pytest.raises(BudgetControlError):
            RegisterExpenseRequestUseCase().execute(
                bootstrapped_conn, account_id=account.id, amount="1500.00",
                request_date=TODAY, operation_id=new_uuid(), requested_by="carla")
        exceeded = bootstrapped_conn.execute(
            "SELECT COUNT(*) FROM finance_outbox WHERE event_name='BUDGET_EXCEEDED'"
        ).fetchone()[0]
        assert exceeded == 1
        with FinanceUnitOfWork(bootstrapped_conn) as uow:
            assert uow.budgets.get(budget.id).lines[0].committed_amount.is_zero()

    def test_submitter_cannot_approve(self, bootstrapped_conn):
        with FinanceUnitOfWork(bootstrapped_conn) as uow:
            account = uow.accounts.get_by_code("6130")
        budget = CreateBudgetUseCase().execute(
            bootstrapped_conn, name="X", fiscal_year=2026,
            lines=[{"account_id": account.id, "period_code": "2026-07",
                    "planned_amount": "1.00"}], operation_id=new_uuid())
        workflow = BudgetWorkflowUseCase()
        workflow.submit(bootstrapped_conn, budget_id=budget.id, submitted_by="ana",
                        operation_id=new_uuid())
        with pytest.raises(FinanceDomainError):
            workflow.approve(bootstrapped_conn, budget_id=budget.id, approved_by="ana",
                             operation_id=new_uuid())


class TestCapitalAndAssets:
    def test_capital_contribution_posts(self, bootstrapped_conn):
        accounts = _accounts_by_type(bootstrapped_conn)
        entry_id = RegisterCapitalMovementUseCase().execute(
            bootstrapped_conn, kind=CapitalMovementKind.CONTRIBUTION, amount="50000.00",
            movement_date=TODAY, treasury_account_id=accounts[TreasuryAccountType.BANK].id,
            counterparty="Socio A", operation_id=new_uuid())
        with FinanceUnitOfWork(bootstrapped_conn) as uow:
            assert uow.journal_entries.get(entry_id).is_balanced()

    def test_asset_capitalization_and_depreciation(self, bootstrapped_conn):
        accounts = _accounts_by_type(bootstrapped_conn)
        fund(bootstrapped_conn, accounts[TreasuryAccountType.BANK].id, "24000.00")
        asset = CapitalizeAssetUseCase().execute(
            bootstrapped_conn, name="Rebanadora", acquisition_cost="24000.00",
            residual_value="0.00", useful_life_months=24,
            capitalization_date=date(2026, 7, 1),
            paid_from_treasury_account_id=accounts[TreasuryAccountType.BANK].id,
            operation_id=new_uuid())
        assert asset.status is FixedAssetStatus.ACTIVE
        uc = RunDepreciationUseCase()
        posted = uc.execute(bootstrapped_conn, year=2026, month=7, operation_id=new_uuid())
        assert len(posted) == 1
        with FinanceUnitOfWork(bootstrapped_conn) as uow:
            assert uow.fixed_assets.get(asset.id).accumulated_depreciation.to_string() == "1000.00"
        # double depreciation of the same period is impossible
        assert uc.execute(bootstrapped_conn, year=2026, month=7, operation_id=new_uuid()) == []
        with FinanceUnitOfWork(bootstrapped_conn) as uow:
            assert uow.fixed_assets.get(asset.id).accumulated_depreciation.to_string() == "1000.00"
            assert len(uow.fixed_assets.list_runs("2026-07")) == 1
