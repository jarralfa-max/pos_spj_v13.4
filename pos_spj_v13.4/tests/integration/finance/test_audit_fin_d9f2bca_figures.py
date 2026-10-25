"""Auditoría directa de Finanzas d9f2bca — cifras confiables.

F04 flujo de efectivo, F05 tesorería, F06 moneda, F13 ejecución de pagos,
F14 saldo promocional, F15 presupuesto, F19 depreciación, F20 precisión,
F22 antigüedad sin vencimiento.
"""

from datetime import date
from decimal import Decimal

import pytest

from backend.application.event_handlers.finance.sale_completed_handler import (
    SaleCompletedHandler,
)
from backend.application.queries.finance.base_finance_query_service import decimal_sum
from backend.application.queries.finance.receivable_query_service import ReceivableQueryService
from backend.application.queries.finance.treasury_query_service import TreasuryQueryService
from backend.application.queries.finance.financial_statement_query_service import (
    FinancialStatementQueryService,
)
from backend.application.queries.finance.base_finance_query_service import LedgerFilter
from backend.application.queries.finance.general_ledger_query_service import (
    GeneralLedgerQueryService,
)
from backend.application.services.finance.posting_engine import PostingEngine
from backend.application.use_cases.finance.approve_expense_use_case import ApproveExpenseUseCase
from backend.application.use_cases.finance.finance_configuration_use_cases import ManageCurrencyUseCase
from backend.application.use_cases.finance.register_expense_request_use_case import RegisterExpenseRequestUseCase
from backend.application.use_cases.finance.accrue_expense_use_case import (
    AccrueExpenseUseCase,
    CancelExpenseUseCase,
)
from backend.application.use_cases.finance.capitalize_asset_use_case import CapitalizeAssetUseCase
from backend.application.use_cases.finance.run_depreciation_use_case import RunDepreciationUseCase
from backend.application.use_cases.finance.authorize_supplier_payment_use_case import AuthorizeSupplierPaymentUseCase
from backend.application.use_cases.finance.create_payable_use_case import CreatePayableUseCase
from backend.application.use_cases.finance.execute_supplier_payment_use_case import ExecuteSupplierPaymentUseCase
from backend.application.use_cases.finance.schedule_supplier_payment_use_case import ScheduleSupplierPaymentUseCase
from backend.application.use_cases.finance.register_collection_use_case import RegisterCollectionUseCase
from backend.application.use_cases.finance.register_sale_credit_charge_use_case import RegisterSaleCreditChargeUseCase
from backend.application.use_cases.finance.register_treasury_transfer_use_case import RegisterTreasuryTransferUseCase
from backend.domain.finance.entities.treasury_account import TreasuryAccount
from backend.domain.finance.enums import (
    FixedAssetStatus,
    JournalType,
    PostingPurpose,
    TreasuryAccountType,
)
from backend.domain.finance.exceptions import (
    CurrencyMismatchError,
    ExchangeRateNotFoundError,
    FinanceDomainError,
    PaymentAuthorizationError,
)
from backend.domain.finance.services.journal_posting_service import (
    JournalPostingService,
    LineSpec,
)
from backend.domain.finance.value_objects.money import Money
from backend.domain.finance.value_objects.posting_reference import PostingReference
from backend.infrastructure.db.repositories.finance.unit_of_work import FinanceUnitOfWork
from backend.shared.ids import new_uuid
from backend.infrastructure.integrations.finance_supplier_directory import SqliteSupplierDirectory
from tests.integration.finance.conftest import account_id, approved_budget, fund, register_supplier

TODAY = date(2026, 7, 16)


def _treasury(conn, account_type=TreasuryAccountType.BANK):
    with FinanceUnitOfWork(conn) as uow:
        return next(a for a in uow.treasury.list_active() if a.account_type is account_type)


def _contribute(conn, amount="100.00", treasury=None):
    return fund(conn, (treasury or _treasury(conn)).id, amount, on=TODAY)


def _position(conn):
    return {row["name"]: row for row in TreasuryQueryService(conn).treasury_position()}


class TestF04DirectCashFlow:
    def _flow(self, conn):
        return FinancialStatementQueryService(conn).cash_flow_statement(
            date_from="2026-07-01", date_to="2026-07-31")

    def test_capital_contribution_is_financing_only(self, bootstrapped_conn):
        _contribute(bootstrapped_conn)
        flow = self._flow(bootstrapped_conn)
        assert flow["financing"] == "100.00"
        assert flow["operating"] == "0.00"
        assert flow["net_change_in_cash"] == "100.00"

    def test_credit_sale_is_not_cash(self, bootstrapped_conn):
        SaleCompletedHandler(bootstrapped_conn).handle({
            "event_id": new_uuid(), "operation_id": new_uuid(), "sale_id": new_uuid(),
            "customer_id": new_uuid(), "occurred_at": "2026-07-16T12:00:00",
            "gross_total": "100.00", "net_total": "100.00",
            "settlements": [{"type": "ON_CREDIT", "amount": "100.00"}]})
        assert self._flow(bootstrapped_conn)["net_change_in_cash"] == "0.00"

    def test_internal_transfer_nets_out_and_net_matches_cash_variation(self, bootstrapped_conn):
        _contribute(bootstrapped_conn, "500.00")
        RegisterTreasuryTransferUseCase().execute(
            bootstrapped_conn, source_treasury_account_id=_treasury(bootstrapped_conn).id,
            target_treasury_account_id=_treasury(
                bootstrapped_conn, TreasuryAccountType.GENERAL_CASH).id,
            amount="200.00", transfer_date=TODAY, operation_id=new_uuid())
        flow = self._flow(bootstrapped_conn)
        assert flow["net_change_in_cash"] == "500.00"
        assert Decimal(flow["closing_cash"]) - Decimal(flow["opening_cash"]) == Decimal("500.00")


class TestF05TreasuryPosition:
    def test_unposted_entry_does_not_move_the_bank(self, bootstrapped_conn):
        bank = _treasury(bootstrapped_conn)
        with FinanceUnitOfWork(bootstrapped_conn) as uow:
            journal = uow.journals.get_by_type(JournalType.BANK)
            period = PostingEngine().resolve_period(uow, TODAY)
            draft = JournalPostingService().build_entry(
                journal.id, "BORRADOR-1", TODAY, period, "Borrador",
                PostingReference("finance", new_uuid(), PostingPurpose.MANUAL, new_uuid()),
                [LineSpec(bank.ledger_account_id, debit=Money.from_string("100.00")),
                 LineSpec(account_id(bootstrapped_conn, "3110"),
                          credit=Money.from_string("100.00"))])
            uow.journal_entries.save(draft)
        assert Decimal(_position(bootstrapped_conn)[bank.name]["balance"]) == 0

    def test_shared_mirror_is_flagged_and_counted_once(self, bootstrapped_conn):
        bank = _treasury(bootstrapped_conn)
        with FinanceUnitOfWork(bootstrapped_conn) as uow:
            uow.treasury.save(TreasuryAccount.create(
                "Banco secundario", TreasuryAccountType.BANK, bank.ledger_account_id))
        _contribute(bootstrapped_conn)
        position = _position(bootstrapped_conn)
        assert position[bank.name]["shared_mirror"]
        assert position["Banco secundario"]["shared_mirror"]
        totals = TreasuryQueryService(bootstrapped_conn).treasury_total()
        assert Decimal(totals["MXN"]) == Decimal("100.00")


class TestF06Currency:
    def test_foreign_currency_without_rate_is_rejected(self, bootstrapped_conn):
        with pytest.raises(ExchangeRateNotFoundError):
            with FinanceUnitOfWork(bootstrapped_conn) as uow:
                PostingEngine().post(
                    uow, JournalType.GENERAL, TODAY, "USD sin tipo de cambio",
                    PostingReference("finance", new_uuid(), PostingPurpose.MANUAL, new_uuid()),
                    [LineSpec(_treasury(bootstrapped_conn).ledger_account_id,
                              debit=Money.from_string("100.00", "USD")),
                     LineSpec(account_id(bootstrapped_conn, "3110"),
                              credit=Money.from_string("100.00", "USD"))])

    def test_ledger_never_adds_two_currencies(self, bootstrapped_conn):
        ManageCurrencyUseCase().register_rate(
            bootstrapped_conn, from_currency="USD", to_currency="MXN", rate="18.50",
            effective_date=date(2026, 7, 1), operation_id=new_uuid(), created_by="t")
        bank = _treasury(bootstrapped_conn).ledger_account_id
        capital = account_id(bootstrapped_conn, "3110")
        engine = PostingEngine()
        for currency in ("MXN", "USD"):
            with FinanceUnitOfWork(bootstrapped_conn) as uow:
                engine.post(uow, JournalType.GENERAL, TODAY, currency,
                            PostingReference("finance", new_uuid(), PostingPurpose.MANUAL,
                                             new_uuid()),
                            [LineSpec(bank, debit=Money.from_string("100.00", currency)),
                             LineSpec(capital, credit=Money.from_string("100.00", currency))])
        rows = {r.account_code: r for r in GeneralLedgerQueryService(
            bootstrapped_conn).account_balances(LedgerFilter())}
        # 100 MXN + 100 USD x 18.50 = 1,950 MXN: nunca 200 "pesos-dolar".
        assert rows["1110"].natural_balance().to_string() == "1950.00"

    def test_entry_lines_cannot_mix_currencies(self, bootstrapped_conn):
        with pytest.raises(CurrencyMismatchError):
            with FinanceUnitOfWork(bootstrapped_conn) as uow:
                PostingEngine().post(
                    uow, JournalType.GENERAL, TODAY, "mezcla",
                    PostingReference("finance", new_uuid(), PostingPurpose.MANUAL, new_uuid()),
                    [LineSpec(_treasury(bootstrapped_conn).ledger_account_id,
                              debit=Money.from_string("100.00", "MXN")),
                     LineSpec(account_id(bootstrapped_conn, "3110"),
                              credit=Money.from_string("100.00", "USD"))])

    def test_mxn_receivable_is_not_collected_into_a_usd_account(self, bootstrapped_conn):
        with FinanceUnitOfWork(bootstrapped_conn) as uow:
            usd = TreasuryAccount.create("Banco USD", TreasuryAccountType.BANK,
                                         account_id(bootstrapped_conn, "1103"),
                                         currency_code="USD")
            uow.treasury.save(usd)
        receivable = RegisterSaleCreditChargeUseCase().execute(
            bootstrapped_conn, customer_id=new_uuid(), sale_id=new_uuid(),
            payment_id=new_uuid(), folio="V-6", amount="100.00", issue_date=TODAY)
        with pytest.raises(CurrencyMismatchError):
            RegisterCollectionUseCase().execute(
                bootstrapped_conn, customer_id=receivable.customer_id, amount="100.00",
                applications=[{"receivable_id": receivable.id, "amount": "100.00"}],
                treasury_account_id=usd.id, collection_date=TODAY, operation_id=new_uuid())
        assert bootstrapped_conn.execute("SELECT COUNT(*) FROM collections").fetchone()[0] == 0


class TestF13PaymentExecutionRevalidates:
    def _authorized(self, conn, **supplier):
        supplier_id = register_supplier(conn, **supplier)
        payable = CreatePayableUseCase().execute(
            conn, supplier_id=supplier_id, amount="100.00", document_number="FP-13",
            issue_date=TODAY, operation_id=new_uuid(),
            counterpart_account_id=account_id(conn, "6130"))
        bank = _treasury(conn)
        _contribute(conn, "500.00", bank)
        payment = ScheduleSupplierPaymentUseCase(SqliteSupplierDirectory(conn)).execute(
            conn, payable_id=payable.id, amount="100.00", scheduled_date=TODAY,
            treasury_account_id=bank.id, scheduled_by=new_uuid(), operation_id=new_uuid())
        AuthorizeSupplierPaymentUseCase().execute(
            conn, payment_id=payment.id, authorized_by=new_uuid(), operation_id=new_uuid())
        return payment, bank, supplier_id

    def test_disabled_treasury_after_authorization_blocks_execution(self, bootstrapped_conn):
        payment, bank, _ = self._authorized(bootstrapped_conn)
        with FinanceUnitOfWork(bootstrapped_conn) as uow:
            bank.active = False
            uow.treasury.update(bank)
        with pytest.raises(FinanceDomainError, match="inactiva"):
            ExecuteSupplierPaymentUseCase(SqliteSupplierDirectory(bootstrapped_conn)).execute(
                bootstrapped_conn, payment_id=payment.id, executed_date=TODAY,
                operation_id=new_uuid(), execution_reference="SPEI-1")

    def test_blocked_supplier_blocks_execution(self, bootstrapped_conn):
        payment, _, supplier_id = self._authorized(bootstrapped_conn)
        bootstrapped_conn.execute(
            "UPDATE proveedores SET bloqueado_financiero=1, motivo_bloqueo='auditoría'"
            " WHERE id=?", (supplier_id,))
        with pytest.raises(PaymentAuthorizationError, match="bloqueados"):
            ExecuteSupplierPaymentUseCase(SqliteSupplierDirectory(bootstrapped_conn)).execute(
                bootstrapped_conn, payment_id=payment.id, executed_date=TODAY,
                operation_id=new_uuid(), execution_reference="SPEI-1")

    def test_unknown_supplier_cannot_be_scheduled(self, bootstrapped_conn):
        register_supplier(bootstrapped_conn)  # hay maestro, pero no este proveedor
        payable = CreatePayableUseCase().execute(
            bootstrapped_conn, supplier_id=new_uuid(), amount="50.00", document_number="FP-X",
            issue_date=TODAY, operation_id=new_uuid(),
            counterpart_account_id=account_id(bootstrapped_conn, "6130"))
        with pytest.raises(PaymentAuthorizationError, match="no existe"):
            ScheduleSupplierPaymentUseCase(SqliteSupplierDirectory(bootstrapped_conn)).execute(
                bootstrapped_conn, payable_id=payable.id, amount="50.00",
                scheduled_date=TODAY, treasury_account_id=_treasury(bootstrapped_conn).id,
                scheduled_by=new_uuid(), operation_id=new_uuid())

    def test_execution_requires_and_keeps_its_evidence(self, bootstrapped_conn):
        payment, _, _ = self._authorized(bootstrapped_conn)
        with pytest.raises(PaymentAuthorizationError, match="evidencia"):
            ExecuteSupplierPaymentUseCase(SqliteSupplierDirectory(bootstrapped_conn)).execute(
                bootstrapped_conn, payment_id=payment.id, executed_date=TODAY,
                operation_id=new_uuid())
        executor = new_uuid()
        ExecuteSupplierPaymentUseCase(SqliteSupplierDirectory(bootstrapped_conn)).execute(
            bootstrapped_conn, payment_id=payment.id, executed_date=TODAY,
            operation_id=new_uuid(), executed_by=executor, execution_reference="SPEI-777")
        row = bootstrapped_conn.execute(
            "SELECT status, executed_by, execution_reference FROM supplier_payments").fetchone()
        assert row == ("EXECUTED", executor, "SPEI-777")


class TestF14PromotionalBalanceIsNotMoney:
    def test_wallet_cannot_transfer_into_the_bank(self, bootstrapped_conn):
        with FinanceUnitOfWork(bootstrapped_conn) as uow:
            wallet = TreasuryAccount.create("Monedero promocional",
                                            TreasuryAccountType.DIGITAL_WALLET,
                                            account_id(bootstrapped_conn, "2134"))
            uow.treasury.save(wallet)
        with pytest.raises(FinanceDomainError, match="no es dinero"):
            RegisterTreasuryTransferUseCase().execute(
                bootstrapped_conn, source_treasury_account_id=wallet.id,
                target_treasury_account_id=_treasury(bootstrapped_conn).id,
                amount="10.00", transfer_date=TODAY, operation_id=new_uuid())
        assert bootstrapped_conn.execute("SELECT COUNT(*) FROM journal_entries").fetchone()[0] == 0


class TestF15BudgetCommitments:
    def _approved(self, conn):
        approved_budget(conn, planned="1000.00")
        return account_id(conn, "6130")

    def _request(self, conn, expense, amount, operation=None):
        request_id = RegisterExpenseRequestUseCase().execute(
            conn, account_id=expense, amount=amount, request_date=TODAY,
            operation_id=operation or new_uuid(), requested_by="ana")
        ApproveExpenseUseCase().approve(conn, expense_request_id=request_id,
                                        approver_id="beto", operation_id=new_uuid())
        return request_id

    def _committed(self, conn):
        return conn.execute("SELECT committed_amount, accrued_amount FROM budget_lines").fetchone()

    def test_replayed_request_commits_once(self, bootstrapped_conn):
        expense, operation = self._approved(bootstrapped_conn), new_uuid()
        register = RegisterExpenseRequestUseCase()
        first, second = (register.execute(
            bootstrapped_conn, account_id=expense, amount="100.00", request_date=TODAY,
            operation_id=operation, requested_by="ana") for _ in range(2))
        ApproveExpenseUseCase().approve(bootstrapped_conn, expense_request_id=first,
                                        approver_id="beto", operation_id=new_uuid())
        assert first == second
        assert self._committed(bootstrapped_conn)[0] == "100.00"
        assert bootstrapped_conn.execute(
            "SELECT COUNT(*) FROM finance_outbox WHERE event_name='BUDGET_COMMITTED'"
        ).fetchone()[0] == 1

    def test_release_and_accrual_close_the_cycle(self, bootstrapped_conn):
        expense = self._approved(bootstrapped_conn)
        cancelled = self._request(bootstrapped_conn, expense, "100.00")
        invoiced = self._request(bootstrapped_conn, expense, "40.00")
        CancelExpenseUseCase().execute(bootstrapped_conn, expense_request_id=cancelled,
                                       reason="Se canceló", operation_id=new_uuid(),
                                       cancelled_by="ana")
        supplier = register_supplier(bootstrapped_conn)
        accrue = AccrueExpenseUseCase()
        accrue.execute(bootstrapped_conn, expense_request_id=invoiced, document_reference="FAC-1",
                       accrual_date=TODAY, operation_id=new_uuid(), accrued_by="carla",
                       supplier_id=supplier)
        assert self._committed(bootstrapped_conn) == ("0.00", "40.00")
        with pytest.raises(FinanceDomainError):
            accrue.execute(bootstrapped_conn, expense_request_id=invoiced,
                           document_reference="FAC-1", accrual_date=TODAY,
                           operation_id=new_uuid(), accrued_by="carla", supplier_id=supplier)


class TestF19DepreciationSchedule:
    def test_last_month_of_useful_life_liquidates_the_rounding(self, bootstrapped_conn):
        _contribute(bootstrapped_conn, "500.00")
        asset = CapitalizeAssetUseCase().execute(
            bootstrapped_conn, name="Equipo", acquisition_cost="100.00",
            useful_life_months=3, capitalization_date=TODAY, operation_id=new_uuid(),
            paid_from_treasury_account_id=_treasury(bootstrapped_conn).id)
        amounts = []
        for month in (7, 8, 9, 10):
            for entry_id in RunDepreciationUseCase().execute(
                    bootstrapped_conn, year=2026, month=month, operation_id=new_uuid()):
                amounts.append(bootstrapped_conn.execute(
                    "SELECT debit_amount FROM journal_lines WHERE journal_entry_id=?"
                    " AND CAST(debit_amount AS REAL) > 0", (entry_id,)).fetchone()[0])
        assert amounts == ["33.33", "33.33", "33.34"]
        with FinanceUnitOfWork(bootstrapped_conn) as uow:
            stored = uow.fixed_assets.get(asset.id)
        # Totalmente depreciado sigue ACTIVO (en uso) hasta su baja.
        assert stored.status is FixedAssetStatus.ACTIVE and stored.is_fully_depreciated


class TestF20Precision:
    def test_monetary_sums_keep_their_cents(self):
        assert decimal_sum(["9007199254740993.01", "0.00"]) == Decimal("9007199254740993.01")

    def test_ledger_balance_keeps_cents_on_a_boundary_amount(self, bootstrapped_conn):
        _contribute(bootstrapped_conn, "9007199254740993.01")
        rows = {r.account_code: r for r in GeneralLedgerQueryService(
            bootstrapped_conn).account_balances(LedgerFilter())}
        assert rows["1110"].natural_balance().to_string() == "9007199254740993.01"


class TestF22AgingWithoutDueDate:
    def test_receivable_without_due_date_is_not_current(self, bootstrapped_conn):
        RegisterSaleCreditChargeUseCase().execute(
            bootstrapped_conn, customer_id=new_uuid(), sale_id=new_uuid(),
            payment_id=new_uuid(), folio="V-22", amount="100.00", issue_date=TODAY)
        rows = ReceivableQueryService(bootstrapped_conn).aging("2027-01-01")
        assert [r["bucket"] for r in rows] == ["NO_DUE_DATE"]
