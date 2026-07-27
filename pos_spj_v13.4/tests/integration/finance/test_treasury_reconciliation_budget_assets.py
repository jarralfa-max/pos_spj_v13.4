"""FASES 9-12 — tesorería, conciliación, presupuestos, capital y activos."""

from datetime import date

import pytest

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
from backend.application.use_cases.finance.reconcile_bank_statement_use_case import (
    ReconcileBankStatementUseCase,
)
from backend.application.use_cases.finance.treasury_use_cases import (
    ImportBankStatementUseCase,
    RegisterTreasuryTransferUseCase,
)
from backend.domain.finance.enums import (
    FixedAssetStatus,
    JournalType,
    PostingPurpose,
    ReconciliationStatus,
    TreasuryAccountType,
)
from backend.domain.finance.exceptions import (
    BudgetControlError,
    FinanceDomainError,
    ReconciliationError,
)
from backend.domain.finance.services.journal_posting_service import LineSpec
from backend.domain.finance.value_objects.money import Money
from backend.domain.finance.value_objects.posting_reference import PostingReference
from backend.infrastructure.db.repositories.finance.unit_of_work import FinanceUnitOfWork
from backend.shared.ids import new_uuid

TODAY = date(2026, 7, 16)


def _accounts_by_type(conn):
    with FinanceUnitOfWork(conn) as uow:
        return {a.account_type: a for a in uow.treasury.list_active()}


class TestTreasury:
    def test_transfer_between_accounts(self, bootstrapped_conn):
        accounts = _accounts_by_type(bootstrapped_conn)
        cash = accounts[TreasuryAccountType.GENERAL_CASH]
        bank = accounts[TreasuryAccountType.BANK]
        entry_id = RegisterTreasuryTransferUseCase().execute(
            bootstrapped_conn, source_treasury_account_id=cash.id,
            target_treasury_account_id=bank.id, amount="5000.00",
            transfer_date=TODAY, operation_id=new_uuid())
        with FinanceUnitOfWork(bootstrapped_conn) as uow:
            entry = uow.journal_entries.get(entry_id)
        assert entry.is_balanced()
        assert entry.total_debits().to_string() == "5000.00"

    def test_transfer_to_same_account_rejected(self, bootstrapped_conn):
        accounts = _accounts_by_type(bootstrapped_conn)
        bank = accounts[TreasuryAccountType.BANK]
        with pytest.raises(FinanceDomainError):
            RegisterTreasuryTransferUseCase().execute(
                bootstrapped_conn, source_treasury_account_id=bank.id,
                target_treasury_account_id=bank.id, amount="1.00",
                transfer_date=TODAY, operation_id=new_uuid())

    def test_transfer_idempotent(self, bootstrapped_conn):
        accounts = _accounts_by_type(bootstrapped_conn)
        op = new_uuid()
        uc = RegisterTreasuryTransferUseCase()
        first = uc.execute(bootstrapped_conn,
                           source_treasury_account_id=accounts[TreasuryAccountType.GENERAL_CASH].id,
                           target_treasury_account_id=accounts[TreasuryAccountType.BANK].id,
                           amount="100.00", transfer_date=TODAY, operation_id=op)
        second = uc.execute(bootstrapped_conn,
                            source_treasury_account_id=accounts[TreasuryAccountType.GENERAL_CASH].id,
                            target_treasury_account_id=accounts[TreasuryAccountType.BANK].id,
                            amount="100.00", transfer_date=TODAY, operation_id=op)
        assert first == second


class TestReconciliation:
    def _bank_inflow(self, conn, amount="1500.00"):
        """Post a bank inflow so a ledger line exists to match."""
        accounts = _accounts_by_type(conn)
        bank = accounts[TreasuryAccountType.BANK]
        engine = PostingEngine()
        with FinanceUnitOfWork(conn) as uow:
            capital = uow.posting_profiles.find_effective("CAPITAL", TODAY)
            entry = engine.post(
                uow, JournalType.BANK, TODAY, "Depósito",
                PostingReference("finance", new_uuid(), PostingPurpose.MANUAL, new_uuid()),
                [
                    LineSpec(bank.ledger_account_id, debit=Money.from_string(amount)),
                    LineSpec(capital.account_for("capital_account_id"),
                             credit=Money.from_string(amount)),
                ],
            )
        bank_line = next(l for l in entry.lines if l.debit.is_positive())
        return bank, bank_line

    def test_import_match_complete_and_revert(self, bootstrapped_conn):
        bank, ledger_line = self._bank_inflow(bootstrapped_conn)
        statement = ImportBankStatementUseCase().execute(
            bootstrapped_conn, treasury_account_id=bank.id, statement_date=TODAY,
            opening_balance="0.00", closing_balance="1500.00",
            lines=[{"transaction_date": "2026-07-16", "description": "DEP",
                    "amount": "1500.00"}],
            operation_id=new_uuid())
        uc = ReconcileBankStatementUseCase()
        reconciliation = uc.start(bootstrapped_conn, bank_statement_id=statement.id,
                                  operation_id=new_uuid())
        uc.match(bootstrapped_conn, reconciliation_id=reconciliation.id,
                 bank_statement_line_id=statement.lines[0].id,
                 journal_line_id=ledger_line.id, matched_by=new_uuid())
        uc.complete(bootstrapped_conn, reconciliation_id=reconciliation.id,
                    completed_by=new_uuid())
        with FinanceUnitOfWork(bootstrapped_conn) as uow:
            stored = uow.reconciliations.get(reconciliation.id)
        assert stored.status is ReconciliationStatus.COMPLETED

        with pytest.raises(ReconciliationError):
            uc.revert(bootstrapped_conn, reconciliation_id=reconciliation.id,
                      reverted_by=new_uuid(), reason="")
        uc.revert(bootstrapped_conn, reconciliation_id=reconciliation.id,
                  reverted_by=new_uuid(), reason="error de captura")
        with FinanceUnitOfWork(bootstrapped_conn) as uow:
            stored = uow.reconciliations.get(reconciliation.id)
        assert stored.status is ReconciliationStatus.REVERTED

    def test_amount_mismatch_cannot_match(self, bootstrapped_conn):
        bank, ledger_line = self._bank_inflow(bootstrapped_conn, amount="1500.00")
        statement = ImportBankStatementUseCase().execute(
            bootstrapped_conn, treasury_account_id=bank.id, statement_date=TODAY,
            opening_balance="0.00", closing_balance="999.00",
            lines=[{"transaction_date": "2026-07-16", "description": "DEP",
                    "amount": "999.00"}],
            operation_id=new_uuid())
        uc = ReconcileBankStatementUseCase()
        reconciliation = uc.start(bootstrapped_conn, bank_statement_id=statement.id,
                                  operation_id=new_uuid())
        with pytest.raises(ReconciliationError):
            uc.match(bootstrapped_conn, reconciliation_id=reconciliation.id,
                     bank_statement_line_id=statement.lines[0].id,
                     journal_line_id=ledger_line.id, matched_by=new_uuid())

    def test_inconsistent_statement_rejected(self, bootstrapped_conn):
        bank, _ = self._bank_inflow(bootstrapped_conn)
        with pytest.raises(ReconciliationError):
            ImportBankStatementUseCase().execute(
                bootstrapped_conn, treasury_account_id=bank.id, statement_date=TODAY,
                opening_balance="0.00", closing_balance="100.00",
                lines=[{"transaction_date": "2026-07-16", "description": "X",
                        "amount": "50.00"}],
                operation_id=new_uuid())


class TestBudgets:
    def _approved_budget(self, conn, planned="10000.00"):
        with FinanceUnitOfWork(conn) as uow:
            expense_account = uow.accounts.get_by_code("6130")
        budget = CreateBudgetUseCase().execute(
            conn, name="OPEX 2026", fiscal_year=2026,
            lines=[{"account_id": expense_account.id, "period_code": "2026-07",
                    "planned_amount": planned}],
            operation_id=new_uuid())
        SubmitBudgetUseCase().execute(conn, budget_id=budget.id, submitted_by=new_uuid())
        ApproveBudgetUseCase().execute(conn, budget_id=budget.id,
                                       approved_by=new_uuid(), operation_id=new_uuid())
        return budget, expense_account

    def test_commitment_within_budget(self, bootstrapped_conn):
        budget, account = self._approved_budget(bootstrapped_conn)
        RegisterExpenseRequestUseCase().execute(
            bootstrapped_conn, account_id=account.id, amount="4000.00",
            request_date=TODAY, operation_id=new_uuid())
        with FinanceUnitOfWork(bootstrapped_conn) as uow:
            stored = uow.budgets.get(budget.id)
        assert stored.lines[0].committed_amount.to_string() == "4000.00"
        assert stored.lines[0].available().to_string() == "6000.00"

    def test_blocking_control_and_exceeded_event(self, bootstrapped_conn):
        budget, account = self._approved_budget(bootstrapped_conn, planned="1000.00")
        with pytest.raises(BudgetControlError):
            RegisterExpenseRequestUseCase().execute(
                bootstrapped_conn, account_id=account.id, amount="1500.00",
                request_date=TODAY, operation_id=new_uuid())
        exceeded = bootstrapped_conn.execute(
            "SELECT COUNT(*) FROM finance_outbox WHERE event_name='BUDGET_EXCEEDED'"
        ).fetchone()[0]
        assert exceeded == 1
        with FinanceUnitOfWork(bootstrapped_conn) as uow:
            stored = uow.budgets.get(budget.id)
        assert stored.lines[0].committed_amount.is_zero()  # rolled back

    def test_submitter_cannot_approve(self, bootstrapped_conn):
        with FinanceUnitOfWork(bootstrapped_conn) as uow:
            account = uow.accounts.get_by_code("6130")
        budget = CreateBudgetUseCase().execute(
            bootstrapped_conn, name="X", fiscal_year=2026,
            lines=[{"account_id": account.id, "period_code": "2026-07",
                    "planned_amount": "1.00"}],
            operation_id=new_uuid())
        user = new_uuid()
        SubmitBudgetUseCase().execute(bootstrapped_conn, budget_id=budget.id, submitted_by=user)
        with pytest.raises(FinanceDomainError):
            ApproveBudgetUseCase().execute(bootstrapped_conn, budget_id=budget.id,
                                           approved_by=user, operation_id=new_uuid())


class TestCapitalAndAssets:
    def test_capital_contribution_posts(self, bootstrapped_conn):
        accounts = _accounts_by_type(bootstrapped_conn)
        entry_id = RegisterCapitalContributionUseCase().execute(
            bootstrapped_conn, amount="50000.00", contribution_date=TODAY,
            treasury_account_id=accounts[TreasuryAccountType.BANK].id,
            contributor="Socio A", operation_id=new_uuid())
        with FinanceUnitOfWork(bootstrapped_conn) as uow:
            entry = uow.journal_entries.get(entry_id)
        assert entry.is_balanced()

    def test_asset_capitalization_and_depreciation(self, bootstrapped_conn):
        accounts = _accounts_by_type(bootstrapped_conn)
        asset = CapitalizeAssetUseCase().execute(
            bootstrapped_conn, name="Rebanadora", acquisition_cost="24000.00",
            residual_value="0.00", useful_life_months=24,
            capitalization_date=date(2026, 7, 1),
            paid_from_treasury_account_id=accounts[TreasuryAccountType.BANK].id,
            operation_id=new_uuid())
        assert asset.status is FixedAssetStatus.CAPITALIZED

        uc = RunDepreciationUseCase()
        posted = uc.execute(bootstrapped_conn, year=2026, month=7, operation_id=new_uuid())
        assert len(posted) == 1
        with FinanceUnitOfWork(bootstrapped_conn) as uow:
            stored = uow.fixed_assets.get(asset.id)
        assert stored.accumulated_depreciation.to_string() == "1000.00"

        # double depreciation of the same period is impossible
        again = uc.execute(bootstrapped_conn, year=2026, month=7, operation_id=new_uuid())
        assert again == []
        with FinanceUnitOfWork(bootstrapped_conn) as uow:
            stored = uow.fixed_assets.get(asset.id)
        assert stored.accumulated_depreciation.to_string() == "1000.00"
