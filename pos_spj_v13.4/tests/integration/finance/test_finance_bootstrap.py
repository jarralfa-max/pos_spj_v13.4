"""FASE 4 — bootstrap: chart of accounts, journals, periods, profiles."""

from datetime import date

from backend.application.services.finance.finance_bootstrap import bootstrap_finance
from backend.domain.finance.enums import CommercialInstrumentType, JournalType
from backend.infrastructure.db.repositories.finance.unit_of_work import FinanceUnitOfWork


class TestBootstrap:
    def test_seeds_chart_journals_period_profiles(self, bootstrapped_conn):
        with FinanceUnitOfWork(bootstrapped_conn) as uow:
            accounts = uow.accounts.list_active()
            journals = uow.journals.list_all()
            period = uow.fiscal_periods.find_by_code(2026, 7)
            profiles = uow.posting_profiles.list_all()
            treasury = uow.treasury.list_active()
        assert len(accounts) >= 40
        assert {j.journal_type for j in journals} == set(JournalType)
        assert period is not None
        assert len(profiles) >= 14
        assert len(treasury) == 3

    def test_bootstrap_is_idempotent(self, bootstrapped_conn):
        bootstrap_finance(bootstrapped_conn, today=date(2026, 7, 16))  # second run
        count = bootstrapped_conn.execute("SELECT COUNT(*) FROM journals").fetchone()[0]
        assert count == len(JournalType)

    def test_profile_resolution_by_instrument(self, bootstrapped_conn):
        with FinanceUnitOfWork(bootstrapped_conn) as uow:
            profile = uow.posting_profiles.find_effective(
                "GIFT_CARD", date(2026, 7, 16),
                instrument_type=CommercialInstrumentType.GIFT_CARD,
            )
        assert profile is not None
        assert profile.has_account("gift_card_liability_account_id")
        assert profile.has_account("breakage_income_account_id")

    def test_profile_effectivity_window(self, bootstrapped_conn):
        with FinanceUnitOfWork(bootstrapped_conn) as uow:
            past = uow.posting_profiles.find_effective("SALE", date(2020, 1, 1))
        assert past is None  # profiles effective from 2026-01-01

    def test_loyalty_profile_has_contra_revenue_and_expense_options(self, bootstrapped_conn):
        """No hardcoded single policy: the profile can express both debit choices."""
        with FinanceUnitOfWork(bootstrapped_conn) as uow:
            profile = uow.posting_profiles.find_effective(
                "LOYALTY_POINTS", date(2026, 7, 16),
                instrument_type=CommercialInstrumentType.LOYALTY_POINTS,
            )
        assert profile.has_account("contra_revenue_account_id")
        assert profile.has_account("expense_account_id")
        assert profile.has_account("liability_account_id")
