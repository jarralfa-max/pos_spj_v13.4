"""Auditoría directa de Finanzas d9f2bca — conciliación, cierre, eventos y UI.

F07/F08 conciliación, F16 cierre, F17 fecha de negocio y perfil de sucursal,
F21 entrega de PAYROLL_PAID, F23 historial de cobros, F24 paginación,
F25 diálogo que explica el rechazo.
"""

import os
from decimal import Decimal
from datetime import date, timedelta, timezone
from types import SimpleNamespace

import pytest

from backend.application.event_handlers.finance.sale_completed_handler import (
    SaleCompletedHandler,
)
from backend.application.queries.finance.journal_query_service import JournalQueryService
from backend.application.queries.finance.receivable_query_service import ReceivableQueryService
from backend.application.services.finance.commercial_reconciliation_service import (
    CommercialReconciliationService,
)
from backend.application.services.finance.posting_engine import PostingEngine
from backend.application.finance.ports import NoOperationalSources
from backend.application.use_cases.finance.authorize_close_exception_use_case import AuthorizeCloseExceptionUseCase
from backend.application.use_cases.finance.create_account_use_case import CreateAccountUseCase
from backend.application.use_cases.finance.close_fiscal_period_use_case import CloseFiscalPeriodUseCase
from backend.application.use_cases.finance.open_fiscal_period_use_case import OpenFiscalPeriodUseCase
from backend.application.use_cases.finance.reconcile_bank_statement_use_case import (
    ReconcileBankStatementUseCase,
)
from backend.application.use_cases.finance.register_collection_use_case import RegisterCollectionUseCase
from backend.application.use_cases.finance.register_sale_credit_charge_use_case import RegisterSaleCreditChargeUseCase
from backend.application.use_cases.finance.import_bank_statement_use_case import ImportBankStatementUseCase
from backend.domain.finance.entities.commercial_obligation import CommercialObligation
from backend.domain.finance.entities.posting_profile import PostingProfile
from backend.domain.finance.enums import (
    AccountType,
    CommercialInstrumentType,
    JournalType,
    PostingPurpose,
    ReconciliationStatus,
    RecognitionBasis,
    TreasuryAccountType,
)
from backend.domain.finance.exceptions import (
    MaterialDifferenceError,
    ClosedFiscalPeriodError,
    ReconciliationError,
)
from backend.domain.finance.services.journal_posting_service import LineSpec
from backend.domain.finance.value_objects.money import Money
from backend.domain.finance.value_objects.posting_reference import PostingReference
from backend.infrastructure.db.repositories.finance.unit_of_work import FinanceUnitOfWork
from backend.shared.events.application_bus import ApplicationEventBus
from backend.shared.ids import new_uuid
from tests.integration.finance.conftest import account_id, fund

TODAY = date(2026, 7, 16)


def _treasury(conn, account_type=TreasuryAccountType.BANK):
    with FinanceUnitOfWork(conn) as uow:
        return next(a for a in uow.treasury.list_active() if a.account_type is account_type)


def _bank_inflow(conn, amount="100.00"):
    entry_id = fund(conn, _treasury(conn).id, amount, on=TODAY)
    bank = _treasury(conn)
    return conn.execute(
        "SELECT id FROM journal_lines WHERE journal_entry_id=? AND account_id=?",
        (entry_id, bank.ledger_account_id)).fetchone()[0]


def _statement(conn, amounts, statement_date=TODAY):
    total = sum((Decimal(a) for a in amounts), Decimal("0"))
    return ImportBankStatementUseCase().execute(
        conn, treasury_account_id=_treasury(conn).id, statement_date=statement_date,
        opening_balance="0.00", closing_balance=str(total),
        lines=[{"transaction_date": statement_date.isoformat(), "description": "MOV",
                "amount": a, "external_reference": new_uuid()} for a in amounts],
        operation_id=new_uuid())


class TestF07EligibleAndUniqueMatches:
    def test_receivable_line_cannot_reconcile_against_the_bank(self, bootstrapped_conn):
        receivable = RegisterSaleCreditChargeUseCase().execute(
            bootstrapped_conn, customer_id=new_uuid(), sale_id=new_uuid(),
            payment_id=new_uuid(), folio="V-7", amount="100.00", issue_date=TODAY)
        RegisterCollectionUseCase().execute(
            bootstrapped_conn, customer_id=receivable.customer_id, amount="100.00",
            applications=[{"receivable_id": receivable.id, "amount": "100.00"}],
            treasury_account_id=_treasury(bootstrapped_conn).id, collection_date=TODAY,
            operation_id=new_uuid())
        cxc_line = bootstrapped_conn.execute(
            "SELECT jl.id FROM journal_lines jl JOIN accounts a ON a.id=jl.account_id"
            " WHERE a.code='1130'").fetchone()[0]
        statement = _statement(bootstrapped_conn, ["-100.00"])
        uc = ReconcileBankStatementUseCase()
        reconciliation = uc.start(bootstrapped_conn, bank_statement_id=statement.id,
                                  operation_id=new_uuid())
        with pytest.raises(ReconciliationError, match="espejo"):
            uc.match(bootstrapped_conn, reconciliation_id=reconciliation.id,
                     bank_statement_line_id=statement.lines[0].id,
                     journal_line_id=cxc_line, matched_by="u")

    def test_same_ledger_line_cannot_back_two_statements(self, bootstrapped_conn):
        line = _bank_inflow(bootstrapped_conn)
        uc = ReconcileBankStatementUseCase()
        first, second = _statement(bootstrapped_conn, ["100.00"]), \
            _statement(bootstrapped_conn, ["100.00"])
        r1 = uc.start(bootstrapped_conn, bank_statement_id=first.id, operation_id=new_uuid())
        r2 = uc.start(bootstrapped_conn, bank_statement_id=second.id, operation_id=new_uuid())
        uc.match(bootstrapped_conn, reconciliation_id=r1.id,
                 bank_statement_line_id=first.lines[0].id, journal_line_id=line, matched_by="u")
        with pytest.raises(ReconciliationError, match="otra partida"):
            uc.match(bootstrapped_conn, reconciliation_id=r2.id,
                     bank_statement_line_id=second.lines[0].id, journal_line_id=line,
                     matched_by="u")


class TestF08CompleteAndRevert:
    def test_unmatched_difference_blocks_completion_unless_declared(self, bootstrapped_conn):
        line = _bank_inflow(bootstrapped_conn)
        statement = _statement(bootstrapped_conn, ["100.00", "100.00"])
        uc = ReconcileBankStatementUseCase()
        reconciliation = uc.start(bootstrapped_conn, bank_statement_id=statement.id,
                                  operation_id=new_uuid())
        uc.match(bootstrapped_conn, reconciliation_id=reconciliation.id,
                 bank_statement_line_id=statement.lines[0].id, journal_line_id=line,
                 matched_by="u")
        with pytest.raises(ReconciliationError, match="sin conciliar"):
            uc.complete(bootstrapped_conn, reconciliation_id=reconciliation.id,
                        completed_by="u")
        uc.complete(bootstrapped_conn, reconciliation_id=reconciliation.id, completed_by="u",
                    difference_reason="Depósito en tránsito")
        with FinanceUnitOfWork(bootstrapped_conn) as uow:
            stored = uow.reconciliations.get(reconciliation.id)
        assert stored.status is ReconciliationStatus.COMPLETED
        assert stored.difference_reason == "Depósito en tránsito"

    def test_revert_releases_the_movements_and_keeps_history(self, bootstrapped_conn):
        line = _bank_inflow(bootstrapped_conn)
        statement = _statement(bootstrapped_conn, ["100.00"])
        uc = ReconcileBankStatementUseCase()
        reconciliation = uc.start(bootstrapped_conn, bank_statement_id=statement.id,
                                  operation_id=new_uuid())
        uc.match(bootstrapped_conn, reconciliation_id=reconciliation.id,
                 bank_statement_line_id=statement.lines[0].id, journal_line_id=line,
                 matched_by="u")
        uc.complete(bootstrapped_conn, reconciliation_id=reconciliation.id, completed_by="u")
        uc.revert(bootstrapped_conn, reconciliation_id=reconciliation.id, reverted_by="jefe",
                  reason="Match equivocado")
        statement_line = bootstrapped_conn.execute(
            "SELECT status FROM bank_statement_lines").fetchone()[0]
        match = bootstrapped_conn.execute(
            "SELECT active, reverted_by FROM reconciliation_matches").fetchone()
        assert statement_line == "UNMATCHED" and match == (0, "jefe")
        candidates = uc.candidates(bootstrapped_conn, reconciliation_id=reconciliation.id)
        assert line in [l["journal_line_id"] for l in candidates["ledger_lines"]]
        # Y se puede volver a conciliar en un estado nuevo.
        again = _statement(bootstrapped_conn, ["100.00"])
        r2 = uc.start(bootstrapped_conn, bank_statement_id=again.id, operation_id=new_uuid())
        uc.match(bootstrapped_conn, reconciliation_id=r2.id,
                 bank_statement_line_id=again.lines[0].id, journal_line_id=line, matched_by="u")


class TestF16PeriodClose:
    def _gift_card(self, conn):
        with FinanceUnitOfWork(conn) as uow:
            uow.commercial_obligations.save(CommercialObligation.recognize(
                CommercialInstrumentType.GIFT_CARD, "loyalty", new_uuid(),
                RecognitionBasis.LIABILITY, Money.from_string("500.00"), new_uuid()))

    def test_material_difference_blocks_until_authorized(self, bootstrapped_conn):
        OpenFiscalPeriodUseCase().execute(bootstrapped_conn, 2026, 7, operation_id=new_uuid())
        self._gift_card(bootstrapped_conn)
        CommercialReconciliationService().reconcile(
            bootstrapped_conn, {"GIFT_CARD": "600.00"}, period_code="2026-07")
        close = CloseFiscalPeriodUseCase(NoOperationalSources())
        with pytest.raises(MaterialDifferenceError, match="diferencias materiales"):
            close.execute(bootstrapped_conn, 2026, 7, closed_by="c", operation_id=new_uuid())
        exception_id = bootstrapped_conn.execute(
            "SELECT id FROM finance_close_exceptions WHERE status='OPEN'").fetchone()[0]
        AuthorizeCloseExceptionUseCase().execute(
            bootstrapped_conn, exception_id=exception_id, authorized_by="contralor",
            reason="Diferencia explicada por tarjetas en tránsito")
        period = close.execute(bootstrapped_conn, 2026, 7, closed_by="c",
                               operation_id=new_uuid())
        assert period.status.value == "CLOSED"

    def test_future_reconciliation_does_not_block_a_prior_month(self, bootstrapped_conn):
        OpenFiscalPeriodUseCase().execute(bootstrapped_conn, 2026, 6, operation_id=new_uuid())
        statement = _statement(bootstrapped_conn, ["10.00"], statement_date=date(2026, 7, 10))
        ReconcileBankStatementUseCase().start(bootstrapped_conn, bank_statement_id=statement.id,
                                              operation_id=new_uuid())
        period = CloseFiscalPeriodUseCase(NoOperationalSources()).execute(
            bootstrapped_conn, 2026, 6, closed_by="c", operation_id=new_uuid())
        assert period.status.value == "CLOSED"

    def test_engine_does_not_open_a_month_before_a_closed_one(self, bootstrapped_conn):
        OpenFiscalPeriodUseCase().execute(bootstrapped_conn, 2026, 6, operation_id=new_uuid())
        CloseFiscalPeriodUseCase(NoOperationalSources()).execute(bootstrapped_conn, 2026, 6, closed_by="c",
                                           operation_id=new_uuid())
        with pytest.raises(ClosedFiscalPeriodError):
            with FinanceUnitOfWork(bootstrapped_conn) as uow:
                PostingEngine().post(
                    uow, JournalType.GENERAL, date(2026, 5, 20), "atrasado",
                    PostingReference("finance", new_uuid(), PostingPurpose.MANUAL, new_uuid()),
                    [LineSpec(_treasury(bootstrapped_conn).ledger_account_id,
                              debit=Money.from_string("1.00")),
                     LineSpec(account_id(bootstrapped_conn, "3110"),
                              credit=Money.from_string("1.00"))])

    def test_subledger_gap_is_persisted_and_blocks(self, bootstrapped_conn):
        OpenFiscalPeriodUseCase().execute(bootstrapped_conn, 2026, 7, operation_id=new_uuid())
        RegisterSaleCreditChargeUseCase().execute(  # auxiliar sin asiento todavía
            bootstrapped_conn, customer_id=new_uuid(), sale_id=new_uuid(),
            payment_id=new_uuid(), folio="V-16", amount="100.00", issue_date=TODAY)
        with pytest.raises(MaterialDifferenceError, match="auxiliar de CxC"):
            CloseFiscalPeriodUseCase(NoOperationalSources()).execute(bootstrapped_conn, 2026, 7, closed_by="c",
                                               operation_id=new_uuid())
        assert bootstrapped_conn.execute(
            "SELECT COUNT(*) FROM finance_close_exceptions WHERE status='OPEN'"
        ).fetchone()[0] == 1


class _MexicoSaleHandler(SaleCompletedHandler):
    business_tz = timezone(timedelta(hours=-6))


class TestF17BusinessDateAndBranchProfile:
    def _sale(self, **overrides):
        payload = {"event_id": new_uuid(), "operation_id": new_uuid(), "sale_id": new_uuid(),
                   "occurred_at": "2026-08-01T00:30:00+00:00", "gross_total": "100.00",
                   "net_total": "100.00", "settlements": [{"type": "CASH", "amount": "100.00"}]}
        payload.update(overrides)
        return payload

    def _entry_date(self, conn, sale_id):
        return conn.execute("SELECT entry_date FROM journal_entries WHERE source_document_id=?",
                            (sale_id,)).fetchone()[0]

    def test_utc_instant_posts_to_the_local_business_day(self, bootstrapped_conn):
        payload = self._sale()
        _MexicoSaleHandler(bootstrapped_conn).handle(payload)
        assert self._entry_date(bootstrapped_conn, payload["sale_id"]) == "2026-07-31"

    def test_producer_business_date_wins(self, bootstrapped_conn):
        payload = self._sale(business_date="2026-07-30")
        SaleCompletedHandler(bootstrapped_conn).handle(payload)
        assert self._entry_date(bootstrapped_conn, payload["sale_id"]) == "2026-07-30"

    def test_branch_profile_decides_the_revenue_account(self, bootstrapped_conn):
        branch = new_uuid()
        north = CreateAccountUseCase().execute(
            bootstrapped_conn, code="4102", name="Ventas sucursal norte",
            account_type=AccountType.REVENUE,
            parent_account_id=account_id(bootstrapped_conn, "4100"),
            branch_restriction_id=branch, operation_id=new_uuid())
        with FinanceUnitOfWork(bootstrapped_conn) as uow:
            generic = uow.posting_profiles.find_effective("SALE", TODAY)
            accounts = dict(generic.accounts)
            accounts["revenue_account_id"] = north.id
            uow.posting_profiles.save(PostingProfile.create(
                "SALE", "Venta sucursal norte", accounts, date(2026, 1, 1), branch_id=branch))
        payload = self._sale(branch_id=branch, occurred_at="2026-07-16T12:00:00")
        SaleCompletedHandler(bootstrapped_conn).handle(payload)
        revenue_code = bootstrapped_conn.execute(
            "SELECT a.code FROM journal_lines jl JOIN accounts a ON a.id=jl.account_id"
            " JOIN journal_entries je ON je.id=jl.journal_entry_id"
            " WHERE je.source_document_id=? AND CAST(jl.credit_amount AS REAL) > 0",
            (payload["sale_id"],)).fetchone()[0]
        assert revenue_code == "4102"


class TestF21PayrollReachesTheLedger:
    def _enqueue(self, conn, payload):
        from backend.infrastructure.db.repositories.hr.support_repositories import (
            HROutboxRepository,
        )
        from backend.infrastructure.db.schema.hr_schema import create_hr_schema
        import json
        create_hr_schema(conn)
        HROutboxRepository(conn).enqueue(new_uuid(), "PAYROLL_PAID", json.dumps(payload),
                                         payload["operation_id"])
        conn.commit()

    def _payload(self, **overrides):
        payload = {"event_id": new_uuid(), "operation_id": new_uuid(),
                   "payroll_run_id": new_uuid(), "paid_at": "2026-07-16T18:00:00+00:00",
                   "gross_salaries": "1000.00", "social_security": "0.00",
                   "net_paid": "900.00"}
        payload.update(overrides)
        return payload

    def test_paid_payroll_is_dispatched_through_the_wired_bus(self, bootstrapped_conn):
        from backend.application.use_cases.hr.finance_wiring import (
            dispatch_hr_outbox,
            wire_hr_finance,
        )
        payload = self._payload()
        self._enqueue(bootstrapped_conn, payload)
        bus = ApplicationEventBus()
        wire_hr_finance(bus, bootstrapped_conn)
        assert dispatch_hr_outbox(bootstrapped_conn, bus)["dispatched"] == 1
        assert dispatch_hr_outbox(bootstrapped_conn, bus)["pending"] == 0  # reentrega: nada
        assert bootstrapped_conn.execute(
            "SELECT COUNT(*) FROM journal_entries WHERE posting_purpose='PAYROLL'"
        ).fetchone()[0] == 1

    def test_unwired_or_failing_delivery_stays_visible(self, bootstrapped_conn):
        from backend.application.use_cases.hr.finance_wiring import (
            dispatch_hr_outbox,
            pending_report,
        )
        self._enqueue(bootstrapped_conn, self._payload())
        result = dispatch_hr_outbox(bootstrapped_conn, ApplicationEventBus())  # sin cableado
        assert result["without_consumer"] == 1
        report = pending_report(bootstrapped_conn)
        assert report[0]["attempts"] == 1 and "consumidor" in report[0]["last_error"]


class TestF23F24ReadModels:
    def test_collection_stays_in_history_after_settlement(self, bootstrapped_conn):
        receivable = RegisterSaleCreditChargeUseCase().execute(
            bootstrapped_conn, customer_id=new_uuid(), sale_id=new_uuid(),
            payment_id=new_uuid(), folio="V-23", amount="100.00", issue_date=TODAY)
        RegisterCollectionUseCase().execute(
            bootstrapped_conn, customer_id=receivable.customer_id, amount="100.00",
            applications=[{"receivable_id": receivable.id, "amount": "100.00"}],
            treasury_account_id=_treasury(bootstrapped_conn).id, collection_date=TODAY,
            reference="REC-1", operation_id=new_uuid())
        service = ReceivableQueryService(bootstrapped_conn)
        history = service.collection_history()
        assert [(h["reference"], h["status"], h["unapplied"]) for h in history]             == [("REC-1", "APPLIED", "0.00")]
        assert [a["document_number"] for a in service.applications(receivable_id=receivable.id)] == ["V-23"]
        assert service.open_receivables() == []

    def test_more_than_200_entries_remain_reachable(self, bootstrapped_conn):
        for _ in range(205):
            fund(bootstrapped_conn, _treasury(bootstrapped_conn).id, "1.00", on=TODAY)
        service = JournalQueryService(bootstrapped_conn)
        assert service.count_entries() == 205
        assert len(service.list_entries(limit=200, offset=200)) == 5


@pytest.fixture(scope="module")
def qapp():
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PyQt5.QtWidgets import QApplication
    return QApplication.instance() or QApplication([])


class TestF25DialogExplainsRejection:
    def test_invalid_transfer_stays_open_and_says_why(self, qapp):
        from frontend.desktop.modules.finance.dialogs.bank_transfer_dialog import (
            BankTransferDialog,
        )
        dialog = BankTransferDialog(None, [("a", "Caja"), ("b", "Banco")])
        dialog.source_combo.setCurrentIndex(0)
        dialog.target_combo.setCurrentIndex(0)
        dialog._accept_if_valid()
        assert not dialog.result()
        assert "distintas" in dialog.error_label.text()
