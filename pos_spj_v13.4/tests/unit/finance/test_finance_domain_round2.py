"""FIN-ERP FASE 1 — reglas de dominio de la ronda 2 (prompt maestro §8, §9, §16, §17, §22, §24, §25, §28)."""

from datetime import date
from decimal import Decimal

import pytest

from backend.domain.finance.entities.account import Account
from backend.domain.finance.entities.audit_record import AuditRecord, mask_account_number
from backend.domain.finance.entities.budget import Budget
from backend.domain.finance.entities.currency import Currency, ExchangeRateRecord
from backend.domain.finance.entities.finance_settings import FinanceSettings
from backend.domain.finance.entities.fiscal_period import FiscalPeriod
from backend.domain.finance.entities.fixed_asset import FixedAsset
from backend.domain.finance.entities.tax import TaxCalculator, TaxRate, TaxRule
from backend.domain.finance.entities.treasury_account import TreasuryAccount
from backend.domain.finance.enums import (
    AccountType,
    AuditAction,
    BudgetControlLevel,
    BudgetStatus,
    FixedAssetStatus,
    JournalEntryStatus,
    LineRole,
    PostingPurpose,
    TreasuryAccountType,
)
from backend.domain.finance.exceptions import (
    AccountInactiveError,
    AccountInUseError,
    AccountNotPostableError,
    AssetNotActiveError,
    BudgetExceededError,
    BudgetNotApprovedError,
    ClosedFiscalPeriodError,
    ExchangeRateNotFoundError,
    FinanceConfigurationError,
    FinanceDomainError,
    InvalidAccountingDateError,
    InvalidMoneyError,
    JournalEntryAlreadyPostedError,
    JournalEntryAlreadyReversedError,
    JournalEntryImmutableError,
    PeriodStateError,
    SegregationOfDutiesError,
    UnbalancedJournalEntryError,
)
from backend.domain.finance.policies.budget_control_policy import BudgetControlPolicy
from backend.domain.finance.policies.segregation_policy import SegregationPolicy
from backend.domain.finance.services.budget_service import BudgetDomainService
from backend.domain.finance.services.journal_posting_service import (
    JournalPostingService,
    LineSpec,
)
from backend.domain.finance.value_objects.account_code import AccountCode
from backend.domain.finance.value_objects.money import Money
from backend.domain.finance.value_objects.posting_reference import PostingReference
from backend.shared.ids import new_uuid


def _ref(purpose=PostingPurpose.MANUAL):
    return PostingReference("finance", new_uuid(), purpose, new_uuid())


def _usd(value: str) -> Money:
    return Money.from_string(value, "USD")


# ── §8.1 plan de cuentas jerárquico ─────────────────────────────────────────
class TestChartHierarchy:
    def test_summary_account_rejects_postings(self):
        group = Account.create("1100", "Activo circulante", AccountType.ASSET,
                               posting_allowed=False)
        with pytest.raises(AccountNotPostableError):
            group.assert_postable()

    def test_inactive_account_raises_specific_error(self):
        account = Account.create("1101", "Caja", AccountType.ASSET)
        account.deactivate()
        with pytest.raises(AccountInactiveError):
            account.assert_postable()

    def test_branch_restricted_account(self):
        branch = new_uuid()
        account = Account.create("1101", "Caja", AccountType.ASSET, branch_restriction_id=branch)
        account.assert_postable(branch_id=branch)
        with pytest.raises(AccountNotPostableError):
            account.assert_postable(branch_id=new_uuid())

    def test_code_hierarchy(self):
        assert AccountCode("1101").is_descendant_of(AccountCode("1100"))
        assert AccountCode("1101").is_descendant_of(AccountCode("1000"))
        assert AccountCode("1105.01").is_descendant_of(AccountCode("1105"))
        assert not AccountCode("2101").is_descendant_of(AccountCode("1000"))
        assert not AccountCode("1100").is_descendant_of(AccountCode("1100"))

    def test_parent_must_be_summary_of_same_type_and_branch(self):
        parent = Account.create("1100", "Activo circulante", AccountType.ASSET,
                                posting_allowed=False)
        parent.assert_can_be_parent_of(Account.create("1101", "Caja", AccountType.ASSET))
        with pytest.raises(FinanceDomainError):
            parent.assert_can_be_parent_of(
                Account.create("1150", "Ingreso mal colgado", AccountType.REVENUE))
        with pytest.raises(FinanceDomainError):
            parent.assert_can_be_parent_of(Account.create("2101", "Otra rama", AccountType.ASSET))
        leaf = Account.create("1101", "Caja", AccountType.ASSET)
        with pytest.raises(FinanceDomainError):
            leaf.assert_can_be_parent_of(Account.create("1102", "Sub", AccountType.ASSET))

    def test_used_account_keeps_its_nature(self):
        account = Account.create("4101", "Ventas", AccountType.REVENUE)
        with pytest.raises(AccountInUseError):
            account.update(account_type=AccountType.EXPENSE, has_movements=True)
        with pytest.raises(AccountInUseError):
            account.update(posting_allowed=False, has_movements=True)
        account.update(name="Ventas netas", has_movements=True)
        assert account.name == "Ventas netas"
        unused = Account.create("4102", "Otra", AccountType.REVENUE)
        unused.update(account_type=AccountType.OTHER_INCOME, has_movements=False)
        assert unused.normal_balance.value == "CREDIT"


# ── §8.3 asiento manual y su ciclo ──────────────────────────────────────────
class TestManualEntryLifecycle:
    def _draft(self):
        service = JournalPostingService()
        period = FiscalPeriod.open_for(2026, 10)
        entry = service.build_entry(
            new_uuid(), "GEN-000001", date(2026, 10, 5), period, "Ajuste manual", _ref(),
            [LineSpec(new_uuid(), debit=Money.from_string("50")),
             LineSpec(new_uuid(), credit=Money.from_string("50"))],
            created_by="ana", validate=False)
        return service, period, entry

    def test_draft_is_editable_until_posted(self):
        service, period, entry = self._draft()
        assert entry.status is JournalEntryStatus.DRAFT
        entry.add_debit(new_uuid(), Money.from_string("10"))
        with pytest.raises(UnbalancedJournalEntryError):
            entry.validate("ana")
        entry.add_credit(new_uuid(), Money.from_string("10"))
        entry.validate("ana")
        assert entry.validated_by == "ana"
        service.post(entry, period, posted_by="beto")
        assert entry.status is JournalEntryStatus.POSTED
        assert entry.posted_by == "beto"
        with pytest.raises(JournalEntryImmutableError):
            entry.replace_lines([])
        with pytest.raises(JournalEntryImmutableError):
            entry.cancel("beto", "error")
        with pytest.raises(JournalEntryAlreadyPostedError):
            entry.mark_posted("beto")

    def test_validated_entry_returns_to_draft(self):
        _, _, entry = self._draft()
        entry.validate("ana")
        entry.return_to_draft()
        assert entry.status is JournalEntryStatus.DRAFT and entry.validated_by is None

    def test_cancelling_a_draft_keeps_who_and_why(self):
        _, _, entry = self._draft()
        entry.cancel("ana", "capturado dos veces")
        assert entry.status is JournalEntryStatus.CANCELLED
        assert entry.cancel_reason == "capturado dos veces"

    def test_lines_carry_dimensions(self):
        service = JournalPostingService()
        period = FiscalPeriod.open_for(2026, 10)
        product, customer, project = new_uuid(), new_uuid(), new_uuid()
        entry = service.build_entry(
            new_uuid(), "GEN-000002", date(2026, 10, 5), period, "Con dimensiones", _ref(),
            [LineSpec(new_uuid(), debit=Money.from_string("20"), product_id=product,
                      customer_id=customer, project_id=project, source_reference="F-1"),
             LineSpec(new_uuid(), credit=Money.from_string("20"))])
        dims = entry.lines[0].dimensions()
        assert dims["product_id"] == product and dims["customer_id"] == customer
        assert dims["project_id"] == project and entry.lines[0].source_reference == "F-1"


# ── §24 moneda extranjera y redondeo visible ───────────────────────────────
class TestForeignCurrency:
    def _post_usd(self, rate, rounding_account="rounding-acc", lines=None):
        service = JournalPostingService()
        period = FiscalPeriod.open_for(2026, 10)
        lines = lines or [
            LineSpec("a1", debit=_usd("10.01")),
            LineSpec("a2", debit=_usd("10.01")),
            LineSpec("a3", credit=_usd("20.02")),
        ]
        return service.build_entry(
            new_uuid(), "BNK-000001", date(2026, 10, 5), period, "Pago en dólares", _ref(),
            lines, currency_code="USD", base_currency_code="MXN",
            exchange_rate=Decimal(rate), rounding_account_id=rounding_account)

    def test_lines_keep_rate_and_base_amounts(self):
        entry = self._post_usd("17.5")
        assert entry.base_currency_code == "MXN"
        first = entry.lines[0]
        assert first.exchange_rate == Decimal("17.5")
        assert first.base_debit.amount == Decimal("175.18")
        assert entry.base_total_debits().amount == entry.base_total_credits().amount

    def test_rounding_difference_goes_to_its_own_visible_line(self):
        entry = self._post_usd("17.3333")
        rounding = [l for l in entry.lines if l.line_role is LineRole.ROUNDING]
        assert len(rounding) == 1
        assert rounding[0].account_id == "rounding-acc"
        assert rounding[0].debit.is_zero() and rounding[0].credit.is_zero()
        assert entry.is_balanced()

    def test_rounding_without_configured_account_fails_loudly(self):
        with pytest.raises(FinanceConfigurationError):
            self._post_usd("17.3333", rounding_account=None)

    def test_foreign_currency_requires_rate(self):
        service = JournalPostingService()
        with pytest.raises(ExchangeRateNotFoundError):
            service.build_entry(
                new_uuid(), "X", date(2026, 10, 5), FiscalPeriod.open_for(2026, 10), "x",
                _ref(), [LineSpec("a", debit=_usd("1")), LineSpec("b", credit=_usd("1"))],
                currency_code="USD", base_currency_code="MXN")

    def test_base_currency_rejects_rate_other_than_one(self):
        with pytest.raises(FinanceConfigurationError):
            JournalPostingService().build_entry(
                new_uuid(), "X", date(2026, 10, 5), FiscalPeriod.open_for(2026, 10), "x",
                _ref(), [LineSpec("a", debit=Money.from_string("1")),
                         LineSpec("b", credit=Money.from_string("1"))],
                exchange_rate=Decimal("2"))

    def test_reversal_of_foreign_entry_mirrors_base_and_rounding(self):
        service = JournalPostingService()
        period = FiscalPeriod.open_for(2026, 10)
        entry = self._post_usd("17.3333")
        service.post(entry, period)
        reversal = service.build_reversal(entry, "BNK-000002", date(2026, 10, 6), period,
                                          "error de captura", _ref(PostingPurpose.REVERSAL))
        assert reversal.base_total_debits().amount == entry.base_total_credits().amount
        assert sum(1 for l in reversal.lines if l.line_role is LineRole.ROUNDING) == 1
        service.post_reversal(entry, reversal, period)
        with pytest.raises(JournalEntryAlreadyReversedError):
            service.build_reversal(entry, "BNK-000003", date(2026, 10, 7), period,
                                   "otra vez", _ref(PostingPurpose.REVERSAL))

    def test_currency_and_rate_records(self):
        usd = Currency.create("usd", "Dólar", decimal_places=2)
        assert usd.code == "USD" and usd.money("1.005").amount == Decimal("1.01")
        with pytest.raises(FinanceDomainError):
            Currency.create("US", "x")
        with pytest.raises(InvalidMoneyError):
            ExchangeRateRecord.create("USD", "MXN", 17.5, date(2026, 10, 1))
        with pytest.raises(FinanceDomainError):
            ExchangeRateRecord.create("MXN", "MXN", "1", date(2026, 10, 1))


# ── §9 periodos ─────────────────────────────────────────────────────────────
class TestPeriodControl:
    def _entry(self, period):
        service = JournalPostingService()
        entry = service.build_entry(
            new_uuid(), "ADJ-1", date(2026, 9, 30), period, "Ajuste", _ref(),
            [LineSpec("a", debit=Money.from_string("1")),
             LineSpec("b", credit=Money.from_string("1"))])
        return service, entry

    def test_soft_closed_period_only_with_special_permission(self):
        period = FiscalPeriod.open_for(2026, 9)
        period.soft_close("contador")
        service, entry = self._entry(period)
        with pytest.raises(ClosedFiscalPeriodError):
            service.post(entry, period)
        service.post(entry, period, allow_soft_closed=True)
        assert entry.status is JournalEntryStatus.POSTED

    def test_closed_period_never_accepts_postings(self):
        period = FiscalPeriod.open_for(2026, 9)
        period.close("contador")
        service, entry = self._entry(period)
        with pytest.raises(ClosedFiscalPeriodError):
            service.post(entry, period, allow_soft_closed=True)

    def test_date_outside_period_is_invalid(self):
        service = JournalPostingService()
        period = FiscalPeriod.open_for(2026, 8)
        entry = service.build_entry(
            new_uuid(), "ADJ-2", date(2026, 9, 30), period, "Fuera", _ref(),
            [LineSpec("a", debit=Money.from_string("1")),
             LineSpec("b", credit=Money.from_string("1"))])
        with pytest.raises(InvalidAccountingDateError):
            service.post(entry, period)

    def test_reopen_records_who_and_requires_reason(self):
        period = FiscalPeriod.open_for(2026, 9)
        period.close("contador")
        with pytest.raises(PeriodStateError):
            period.reopen("  ", "director")
        period.reopen("Factura omitida", "director")
        assert period.reopened_by == "director" and period.reopen_reason == "Factura omitida"
        assert period.start_date == date(2026, 9, 1) and period.end_date == date(2026, 9, 30)


# ── §28 segregación ─────────────────────────────────────────────────────────
class TestSegregation:
    def test_creator_cannot_post_own_manual_entry_when_review_required(self):
        policy = SegregationPolicy(FinanceSettings())
        with pytest.raises(SegregationOfDutiesError):
            policy.enforce_journal_posting(created_by="ana", posted_by="ana")
        policy.enforce_journal_posting(created_by="ana", posted_by="beto")
        relaxed = SegregationPolicy(FinanceSettings(journal_review_required=False))
        relaxed.enforce_journal_posting(created_by="ana", posted_by="ana")

    def test_payment_steps(self):
        policy = SegregationPolicy(FinanceSettings(
            payment_second_authorization_threshold=Decimal("10000")))
        with pytest.raises(SegregationOfDutiesError):
            policy.enforce_payment_authorization(scheduled_by="ana", authorizer="ana")
        with pytest.raises(SegregationOfDutiesError):
            policy.enforce_payment_authorization(scheduled_by="ana", authorizer="beto",
                                                 first_authorizer="beto")
        with pytest.raises(SegregationOfDutiesError):
            policy.enforce_payment_execution(authorized_by="beto", second_authorized_by=None,
                                             executor="beto")
        policy.enforce_payment_execution(authorized_by="beto", second_authorized_by="caro",
                                         executor="dani")
        assert policy.requires_second_authorization(Money.from_string("10000"))
        assert not policy.requires_second_authorization(Money.from_string("9999.99"))
        assert not SegregationPolicy(FinanceSettings()).requires_second_authorization(
            Money.from_string("1000000"))

    def test_statement_importer_cannot_approve_own_adjustment(self):
        policy = SegregationPolicy(FinanceSettings())
        with pytest.raises(SegregationOfDutiesError):
            policy.enforce_statement_adjustment(imported_by="ana", adjuster="ana")


# ── configuración ───────────────────────────────────────────────────────────
class TestFinanceSettings:
    def test_round_trip_and_coercion(self):
        settings = FinanceSettings().with_changes(
            payment_second_authorization_threshold="25000.00",
            reconciliation_date_window_days="3", journal_review_required="0")
        stored = settings.as_storage()
        assert stored["payment_second_authorization_threshold"] == "25000.00"
        assert stored["budget_warning_percent"] == ""
        again = FinanceSettings.from_storage(stored)
        assert again == settings
        assert again.journal_review_required is False

    def test_rejects_float_negative_and_unknown(self):
        with pytest.raises(FinanceDomainError):
            FinanceSettings().with_changes(budget_warning_percent=80.0)
        with pytest.raises(FinanceDomainError):
            FinanceSettings().with_changes(reconciliation_amount_tolerance="-1")
        with pytest.raises(FinanceDomainError):
            FinanceSettings().with_changes(unknown_key="1")
        with pytest.raises(FinanceDomainError):
            FinanceSettings().with_changes(base_currency_code="PESOS")


# ── §22 impuestos ───────────────────────────────────────────────────────────
class TestTaxes:
    def test_inclusive_split_never_loses_a_cent(self):
        breakdown = TaxCalculator.from_inclusive(Money.from_string("100.00"), Decimal("16"))
        assert breakdown.base.amount == Decimal("86.21")
        assert breakdown.tax.amount == Decimal("13.79")
        assert breakdown.total.amount == Decimal("100.00")

    def test_zero_rate_keeps_the_whole_amount_as_base(self):
        breakdown = TaxCalculator.from_inclusive(Money.from_string("250.00"), Decimal("0"))
        assert breakdown.tax.is_zero() and breakdown.base.amount == Decimal("250.00")

    def test_rate_validity_and_rules(self):
        rate = TaxRate.create(new_uuid(), "16", date(2026, 1, 1), date(2026, 12, 31))
        assert rate.applies_on(date(2026, 6, 1)) and not rate.applies_on(date(2027, 1, 1))
        with pytest.raises(FinanceDomainError):
            TaxRate.create(new_uuid(), "116", date(2026, 1, 1))
        with pytest.raises(InvalidMoneyError):
            TaxRate.create(new_uuid(), 16.0, date(2026, 1, 1))
        with pytest.raises(FinanceDomainError):
            TaxRule.create(new_uuid(), "PRODUCT", None, date(2026, 1, 1))
        assert TaxRule.create(new_uuid(), "DEFAULT", "x", date(2026, 1, 1)).scope_id is None


# ── §16 presupuesto ─────────────────────────────────────────────────────────
class TestBudgetControl:
    def _approved(self, blocking=True):
        budget = Budget.create("Operación 2026", 2026, new_uuid(), blocking=blocking)
        line = budget.add_line("acct", "2026-10", Money.from_string("1000"))
        budget.submit("ana")
        budget.approve("beto")
        return budget, line

    def test_commitment_accrual_payment_formula(self):
        budget, line = self._approved()
        service = BudgetDomainService()
        service.commit(budget, "acct", "2026-10", Money.from_string("300"))
        service.accrue(budget, "acct", "2026-10", Money.from_string("300"),
                       from_commitment=Money.from_string("300"))
        service.pay(budget, "acct", "2026-10", Money.from_string("100"))
        assert line.committed_amount.amount == 0
        assert line.accrued_amount.amount == Decimal("200")
        assert line.paid_amount.amount == Decimal("100")
        assert line.available().amount == Decimal("700")

    def test_warning_then_blocking_then_authorized_excess(self):
        budget, line = self._approved()
        service = BudgetDomainService(warning_percent=Decimal("80"))
        _, level = service.commit(budget, "acct", "2026-10", Money.from_string("850"))
        assert level is BudgetControlLevel.WARNING
        with pytest.raises(BudgetExceededError):
            service.commit(budget, "acct", "2026-10", Money.from_string("200"))
        _, level = service.commit(budget, "acct", "2026-10", Money.from_string("200"),
                                  excess_authorized=True)
        assert level is BudgetControlLevel.BLOCKING
        assert line.available().amount == Decimal("-50")

    def test_non_blocking_budget_only_warns(self):
        budget, _ = self._approved(blocking=False)
        _, level = BudgetDomainService().commit(budget, "acct", "2026-10",
                                                Money.from_string("1500"))
        assert level is BudgetControlLevel.BLOCKING

    def test_unapproved_budget_does_not_control(self):
        budget = Budget.create("Borrador", 2026, new_uuid())
        budget.add_line("acct", "2026-10", Money.from_string("10"))
        with pytest.raises(BudgetNotApprovedError):
            BudgetDomainService().commit(budget, "acct", "2026-10", Money.from_string("1"))

    def test_reject_returns_to_draft_and_lifecycle(self):
        budget = Budget.create("B", 2026, new_uuid())
        budget.add_line("acct", "2026-10", Money.from_string("10"))
        budget.submit("ana")
        budget.reject("faltan sucursales")
        assert budget.status is BudgetStatus.DRAFT and budget.rejection_reason
        budget.submit("ana")
        budget.approve("beto")
        budget.activate()
        assert budget.status is BudgetStatus.ACTIVE and budget.controls_spending
        BudgetDomainService().commit(budget, "acct", "2026-10", Money.from_string("1"))
        with pytest.raises(FinanceDomainError):
            budget.cancel("ya no")
        budget.close()
        assert budget.status is BudgetStatus.CLOSED


# ── §17 activos ─────────────────────────────────────────────────────────────
class TestFixedAssetLifecycle:
    def _active(self):
        asset = FixedAsset.create("Báscula", Money.from_string("1200"), Money.from_string("0"),
                                  12, new_uuid(), asset_code="ac-1",
                                  acquisition_date=date(2026, 1, 10))
        asset.capitalize(date(2026, 1, 15), "a", "d", "acc")
        return asset

    def test_suspended_asset_does_not_depreciate(self):
        asset = self._active()
        asset.suspend("En reparación")
        with pytest.raises(AssetNotActiveError):
            asset.register_depreciation(Money.from_string("100"), "2026-01")
        asset.resume()
        asset.register_depreciation(Money.from_string("100"), "2026-01")
        assert asset.book_value.amount == Decimal("1100") and asset.asset_code == "AC-1"

    def test_fully_depreciated_asset_stays_active(self):
        asset = self._active()
        asset.register_depreciation(Money.from_string("1200"), "2026-01")
        assert asset.is_fully_depreciated and asset.status is FixedAssetStatus.ACTIVE

    def test_retirement_states(self):
        asset = self._active()
        asset.retire(FixedAssetStatus.SOLD, date(2026, 6, 1), new_uuid(), "Vendida")
        assert asset.status is FixedAssetStatus.SOLD
        with pytest.raises(AssetNotActiveError):
            asset.retire(FixedAssetStatus.WRITTEN_OFF, date(2026, 6, 2), new_uuid())

    def test_service_date_not_before_acquisition(self):
        asset = FixedAsset.create("X", Money.from_string("10"), Money.from_string("0"), 1,
                                  new_uuid(), acquisition_date=date(2026, 5, 1))
        with pytest.raises(FinanceDomainError):
            asset.capitalize(date(2026, 4, 1), "a", "d", "acc")


# ── §25 auditoría / enmascarado ─────────────────────────────────────────────
class TestAuditAndMasking:
    def test_bank_numbers_are_masked(self):
        assert mask_account_number("012 3456 7890 1234 5678") == "••••5678"
        treasury = TreasuryAccount.create("Banco", TreasuryAccountType.BANK, "acc",
                                          account_number="012345678901234567")
        assert treasury.masked_account_number == "••••4567"
        assert not hasattr(treasury, "bank_account_number")

    def test_audit_record_scrubs_before_and_after(self):
        record = AuditRecord.create(
            action=AuditAction.TREASURY_MOVEMENT, entity_type="treasury_account",
            entity_id=new_uuid(), operation_id=new_uuid(), user_id="ana",
            before={"bank_account_number": "012345678901234567", "amount": "10"},
            after={"amount": "20"}, reason="ajuste")
        assert "012345678901234567" not in record.before_json
        assert "4567" in record.before_json and '"amount": "20"' in record.after_json
