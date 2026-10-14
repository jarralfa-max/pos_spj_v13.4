"""Auditoría directa de Finanzas d9f2bca — integridad y acceso.

Cada prueba reproduce el escenario del anexo de la auditoría y fija el
criterio de aceptación corregido (F01, F02, F03, F09, F10, F11, F12, F18).
"""

from datetime import date
from types import SimpleNamespace

import pytest

from backend.application.event_handlers.finance.procurement_payable_bridge import (
    ProcurementPayableBridgeHandler,
)
from backend.application.event_handlers.finance.sale_completed_handler import (
    SaleCompletedHandler,
)
from backend.application.event_handlers.finance.sale_returned_handler import (
    SaleReturnedHandler,
)
from backend.application.finance.authorization import (
    AllowAllFinancePermissionCheckerForTests,
    DenyAllFinancePermissionCheckerForTests,
    FinanceAuthorizationPolicy,
    FinanceSessionPermissionChecker,
)
from backend.application.finance.finance_commands import FinanceCommandService
from backend.application.finance.permissions import FinancePermissions
from backend.application.services.finance.posting_engine import PostingEngine
from backend.application.use_cases.finance.capital_and_asset_use_cases import (
    CapitalizeAssetUseCase,
)
from backend.application.use_cases.finance.receivable_use_cases import (
    CreateReceivableUseCase,
    RegisterCollectionUseCase,
    RegisterSaleCreditChargeUseCase,
)
from backend.domain.finance.entities.commercial_obligation import CommercialObligation
from backend.domain.finance.enums import (
    CommercialInstrumentType,
    JournalType,
    PostingPurpose,
    RecognitionBasis,
    TreasuryAccountType,
)
from backend.domain.finance.exceptions import (
    ConcurrencyConflictError,
    FinanceDomainError,
    FinancePermissionDeniedError,
    IdempotencyConflictError,
)
from backend.domain.finance.services.journal_posting_service import LineSpec
from backend.domain.finance.value_objects.money import Money
from backend.domain.finance.value_objects.posting_reference import PostingReference
from backend.infrastructure.db.repositories.finance.unit_of_work import FinanceUnitOfWork
from backend.shared.ids import new_uuid
from frontend.desktop.modules.finance.finance_routes import build_finance_presenter
from tests.integration.finance.conftest import account_id, register_supplier

TODAY = date(2026, 7, 16)


def _treasury(conn, account_type=TreasuryAccountType.BANK):
    with FinanceUnitOfWork(conn) as uow:
        return next(a for a in uow.treasury.list_active() if a.account_type is account_type)


def _count(conn, sql, params=()):
    return conn.execute(sql, params).fetchone()[0]


def _ledger(conn, code):
    rows = conn.execute(
        "SELECT jl.debit_amount, jl.credit_amount FROM journal_lines jl"
        " JOIN journal_entries je ON je.id=jl.journal_entry_id"
        " JOIN accounts a ON a.id=jl.account_id WHERE a.code=? AND je.status='POSTED'",
        (code,)).fetchall()
    from decimal import Decimal
    return sum((Decimal(d) - Decimal(c) for d, c in rows), Decimal("0"))


def _session(user_id, granted: set[str]):
    return SimpleNamespace(user_id=user_id, is_active=True, active_branch_id="b1",
                           tiene_permiso=lambda code: code in granted)


class TestF01SingleTransactionOwner:
    def test_nested_finance_write_dies_with_the_sale_rollback(self, bootstrapped_conn):
        RegisterSaleCreditChargeUseCase().execute(
            bootstrapped_conn, customer_id=new_uuid(), sale_id=new_uuid(),
            payment_id=new_uuid(), folio="V-1", amount="100.00", issue_date=TODAY,
            owns_transaction=False)
        bootstrapped_conn.rollback()  # la venta falla después
        assert _count(bootstrapped_conn, "SELECT COUNT(*) FROM receivables") == 0

    def test_procurement_posting_failure_leaves_no_payable(self, bootstrapped_conn):
        payload = {
            "source_module": "procurement", "supplier_id": new_uuid(),
            "document_number": "FAC-90", "document_id": new_uuid(), "amount": "100.00",
            "operation_id": new_uuid(), "timestamp": "2026-07-16T12:00:00",
            "nature_subtotals": {"INVENTORY": "90.00"},  # reconocimiento 90 ≠ obligación 100
        }
        with pytest.raises(FinanceDomainError):
            ProcurementPayableBridgeHandler(bootstrapped_conn).handle(payload)
        assert _count(bootstrapped_conn, "SELECT COUNT(*) FROM payables") == 0
        assert _count(bootstrapped_conn, "SELECT COUNT(*) FROM journal_entries") == 0


class TestF02CommandAuthorization:
    def test_read_only_session_cannot_register_a_transfer(self, bootstrapped_conn):
        user = new_uuid()
        presenter = build_finance_presenter(
            bootstrapped_conn, _session(user, {FinancePermissions.VIEW}))
        cash = _treasury(bootstrapped_conn, TreasuryAccountType.GENERAL_CASH)
        bank = _treasury(bootstrapped_conn)
        ok, message = presenter.register_treasury_transfer(
            source_id=cash.id, target_id=bank.id, amount="10.00", reference="x")
        assert not ok and "FINANZAS.tesoreria.transferir" in message
        assert _count(bootstrapped_conn, "SELECT COUNT(*) FROM journal_entries") == 0

    def test_missing_session_cannot_register_a_capital_contribution(self, bootstrapped_conn):
        presenter = build_finance_presenter(bootstrapped_conn, None)
        ok, _ = presenter.register_capital_contribution(
            amount="100.00", treasury_account_id=_treasury(bootstrapped_conn).id,
            contributor="socio")
        assert not ok
        assert _count(bootstrapped_conn, "SELECT COUNT(*) FROM journal_entries") == 0

    def test_authorized_transfer_carries_the_actor(self, bootstrapped_conn):
        user = new_uuid()
        presenter = build_finance_presenter(
            bootstrapped_conn, _session(user, {FinancePermissions.TREASURY_TRANSFER}))
        ok, _ = presenter.register_treasury_transfer(
            source_id=_treasury(bootstrapped_conn, TreasuryAccountType.GENERAL_CASH).id,
            target_id=_treasury(bootstrapped_conn).id, amount="10.00", reference="x")
        assert ok
        assert bootstrapped_conn.execute(
            "SELECT created_by FROM journal_entries").fetchone()[0] == user

    def test_direct_command_invocation_is_rejected_without_permission(self, bootstrapped_conn):
        service = FinanceCommandService(
            connection_provider=lambda: bootstrapped_conn, use_cases={},
            authorization=FinanceAuthorizationPolicy(DenyAllFinancePermissionCheckerForTests()),
            actor_provider=lambda: new_uuid())
        for call in (lambda: service.capital_contribution(amount="1", treasury_account_id="x"),
                     lambda: service.authorize_payment("p"),
                     lambda: service.close_period(2026, 7, soft=False),
                     lambda: service.reverse_entry("e", reason="r")):
            with pytest.raises(FinancePermissionDeniedError):
                call()

    def test_absent_actor_is_rejected_even_with_permissive_checker(self, bootstrapped_conn):
        service = FinanceCommandService(
            connection_provider=lambda: bootstrapped_conn, use_cases={},
            authorization=FinanceAuthorizationPolicy(AllowAllFinancePermissionCheckerForTests()),
            actor_provider=lambda: None)
        with pytest.raises(FinancePermissionDeniedError):
            service.treasury_transfer(source_id="a", target_id="b", amount="1")

    def test_authorizing_a_payment_needs_the_permission_not_just_another_id(self):
        session = _session("u2", {FinancePermissions.PAYMENT_SCHEDULE})
        policy = FinanceAuthorizationPolicy(FinanceSessionPermissionChecker(session))
        with pytest.raises(FinancePermissionDeniedError):
            policy.require("u2", FinancePermissions.PAYMENT_AUTHORIZE)


class TestF03SeparateCreditPayments:
    def test_two_credit_payments_owe_their_sum_and_replays_change_nothing(self, bootstrapped_conn):
        uc, sale, customer = RegisterSaleCreditChargeUseCase(), new_uuid(), new_uuid()
        first, second = new_uuid(), new_uuid()
        for payment_id, amount in ((first, "10.00"), (second, "20.00"),
                                   (first, "10.00"), (second, "20.00")):
            receivable = uc.execute(bootstrapped_conn, customer_id=customer, sale_id=sale,
                                    payment_id=payment_id, folio="V-7", amount=amount,
                                    issue_date=TODAY)
        with FinanceUnitOfWork(bootstrapped_conn) as uow:
            stored = uow.receivables.get(receivable.id)
            document = uow.financial_documents.get(stored.financial_document_id)
        assert stored.outstanding_amount.to_string() == "30.00"
        assert document.outstanding_amount.to_string() == "30.00"
        assert _count(bootstrapped_conn, "SELECT COUNT(*) FROM receivable_charges") == 2

    def test_completed_sale_posts_the_same_credit_as_the_exposure(self, bootstrapped_conn):
        uc, sale, customer = RegisterSaleCreditChargeUseCase(), new_uuid(), new_uuid()
        uc.execute(bootstrapped_conn, customer_id=customer, sale_id=sale, payment_id=new_uuid(),
                   folio="V-8", amount="10.00", issue_date=TODAY)
        uc.execute(bootstrapped_conn, customer_id=customer, sale_id=sale, payment_id=new_uuid(),
                   folio="V-8", amount="20.00", issue_date=TODAY)
        SaleCompletedHandler(bootstrapped_conn).handle({
            "event_id": new_uuid(), "operation_id": new_uuid(), "sale_id": sale,
            "folio": "V-8", "customer_id": customer, "occurred_at": "2026-07-16T12:00:00",
            "gross_total": "30.00", "net_total": "30.00",
            "settlements": [{"type": "ON_CREDIT", "amount": "30.00"}]})
        assert str(_ledger(bootstrapped_conn, "1130")) == "30.00"
        assert _count(bootstrapped_conn, "SELECT COUNT(*) FROM finance_close_exceptions") == 0


class TestF09F10Idempotency:
    def _gift_card(self, conn, amount="100.00"):
        instrument = new_uuid()
        with FinanceUnitOfWork(conn) as uow:
            uow.commercial_obligations.save(CommercialObligation.recognize(
                CommercialInstrumentType.GIFT_CARD, "loyalty", instrument,
                RecognitionBasis.LIABILITY, Money.from_string(amount), new_uuid()))
        return instrument

    def test_reissued_sale_event_redeems_the_instrument_once(self, bootstrapped_conn):
        instrument = self._gift_card(bootstrapped_conn)
        payload = {"operation_id": new_uuid(), "sale_id": new_uuid(), "folio": "V-9",
                   "occurred_at": "2026-07-16T12:00:00", "gross_total": "10.00",
                   "net_total": "10.00",
                   "settlements": [{"type": "GIFT_CARD", "amount": "10.00",
                                    "instrument_id": instrument}]}
        handler = SaleCompletedHandler(bootstrapped_conn)
        handler.handle({**payload, "event_id": new_uuid()})
        handler.handle({**payload, "event_id": new_uuid()})  # sobre nuevo, misma venta
        with FinanceUnitOfWork(bootstrapped_conn) as uow:
            obligation = uow.commercial_obligations.find_by_instrument(
                CommercialInstrumentType.GIFT_CARD, instrument)
        assert obligation.redeemed_amount.to_string() == "10.00"
        assert _count(bootstrapped_conn,
                      "SELECT COUNT(*) FROM journal_entries WHERE posting_purpose='SALE_REVENUE'") == 1

    def test_same_operation_with_other_content_is_a_conflict(self, bootstrapped_conn):
        engine, bank = PostingEngine(), _treasury(bootstrapped_conn)
        capital = account_id(bootstrapped_conn, "3110")
        reference = PostingReference("finance", new_uuid(), PostingPurpose.MANUAL, new_uuid())

        def _post(amount):
            with FinanceUnitOfWork(bootstrapped_conn) as uow:
                return engine.post(uow, JournalType.GENERAL, TODAY, "x", reference, [
                    LineSpec(bank.ledger_account_id, debit=Money.from_string(amount)),
                    LineSpec(capital, credit=Money.from_string(amount))])

        first = _post("100.00")
        assert _post("100.00").id == first.id
        with pytest.raises(IdempotencyConflictError):
            _post("200.00")
        assert _count(bootstrapped_conn, "SELECT COUNT(*) FROM journal_entries") == 1

    def test_receivable_key_reused_with_other_amount_is_a_conflict(self, bootstrapped_conn):
        operation, customer = new_uuid(), new_uuid()
        kwargs = dict(customer_id=customer, document_number="F-1", issue_date=TODAY,
                      operation_id=operation,
                      counterpart_account_id=account_id(bootstrapped_conn, "4101"))
        CreateReceivableUseCase().execute(bootstrapped_conn, amount="100.00", **kwargs)
        with pytest.raises(IdempotencyConflictError):
            CreateReceivableUseCase().execute(bootstrapped_conn, amount="200.00", **kwargs)


class TestF11SubledgerAndLedgerAgree:
    def test_receivable_from_finance_requires_its_recognition(self, bootstrapped_conn):
        with pytest.raises(FinanceDomainError, match="contrapartida"):
            CreateReceivableUseCase().execute(
                bootstrapped_conn, customer_id=new_uuid(), amount="100.00",
                document_number="F-2", issue_date=TODAY, operation_id=new_uuid())

    def test_collecting_a_recognized_receivable_leaves_both_at_zero(self, bootstrapped_conn):
        receivable = CreateReceivableUseCase().execute(
            bootstrapped_conn, customer_id=new_uuid(), amount="100.00", document_number="F-3",
            issue_date=TODAY, operation_id=new_uuid(),
            counterpart_account_id=account_id(bootstrapped_conn, "4101"))
        RegisterCollectionUseCase().execute(
            bootstrapped_conn, receivable_id=receivable.id, amount="100.00",
            treasury_account_id=_treasury(bootstrapped_conn).id, collection_date=TODAY,
            operation_id=new_uuid())
        assert str(_ledger(bootstrapped_conn, "1130")) == "0.00"

    def test_unpaid_capex_creates_its_payable(self, bootstrapped_conn):
        with pytest.raises(FinanceDomainError, match="proveedor"):
            CapitalizeAssetUseCase().execute(
                bootstrapped_conn, name="Báscula", acquisition_cost="100.00",
                useful_life_months=12, capitalization_date=TODAY, operation_id=new_uuid())
        CapitalizeAssetUseCase().execute(
            bootstrapped_conn, name="Báscula", acquisition_cost="100.00",
            useful_life_months=12, capitalization_date=TODAY, operation_id=new_uuid(),
            supplier_id=register_supplier(bootstrapped_conn))
        assert _count(bootstrapped_conn, "SELECT COUNT(*) FROM payables") == 1
        assert bootstrapped_conn.execute(
            "SELECT outstanding_amount FROM payables").fetchone()[0] == "100.00"
        assert str(-_ledger(bootstrapped_conn, "2101")) == "100.00"


class TestF12CreditNoteAppliedToTheInvoice:
    def test_return_reduces_document_and_receivable_once(self, bootstrapped_conn):
        sale, customer = new_uuid(), new_uuid()
        SaleCompletedHandler(bootstrapped_conn).handle({
            "event_id": new_uuid(), "operation_id": new_uuid(), "sale_id": sale,
            "folio": "V-12", "customer_id": customer, "occurred_at": "2026-07-16T12:00:00",
            "gross_total": "100.00", "net_total": "100.00",
            "settlements": [{"type": "ON_CREDIT", "amount": "100.00"}]})
        refund = {"operation_id": new_uuid(), "sale_id": sale, "return_id": new_uuid(),
                  "folio": "V-12", "customer_id": customer,
                  "occurred_at": "2026-07-16T13:00:00", "amount": "20.00",
                  "gross_amount": "20.00",
                  "refunds": [{"type": "ON_CREDIT", "amount": "20.00"}]}
        SaleReturnedHandler(bootstrapped_conn).handle({**refund, "event_id": new_uuid()})
        SaleReturnedHandler(bootstrapped_conn).handle({**refund, "event_id": new_uuid()})
        receivable = bootstrapped_conn.execute(
            "SELECT outstanding_amount FROM receivables").fetchone()[0]
        document = bootstrapped_conn.execute(
            "SELECT outstanding_amount FROM financial_documents"
            " WHERE document_type='SALES_INVOICE'").fetchone()[0]
        assert receivable == "80.00" and document == "80.00"


class TestF18OptimisticConcurrency:
    def test_stale_write_is_rejected_and_keeps_the_first(self, bootstrapped_conn):
        receivable = CreateReceivableUseCase().execute(
            bootstrapped_conn, customer_id=new_uuid(), amount="100.00", document_number="F-18",
            issue_date=TODAY, operation_id=new_uuid(),
            counterpart_account_id=account_id(bootstrapped_conn, "4101"))
        with FinanceUnitOfWork(bootstrapped_conn) as uow:
            copy_a = uow.receivables.get(receivable.id)
            copy_b = uow.receivables.get(receivable.id)
        copy_a.apply_collection(Money.from_string("30.00"))
        copy_b.apply_collection(Money.from_string("20.00"))
        with FinanceUnitOfWork(bootstrapped_conn) as uow:
            uow.receivables.update(copy_a)
        with pytest.raises(ConcurrencyConflictError):
            with FinanceUnitOfWork(bootstrapped_conn) as uow:
                uow.receivables.update(copy_b)
        with FinanceUnitOfWork(bootstrapped_conn) as uow:
            fresh = uow.receivables.get(receivable.id)
        fresh.apply_collection(Money.from_string("20.00"))  # recargar y revalidar
        with FinanceUnitOfWork(bootstrapped_conn) as uow:
            uow.receivables.update(fresh)
            assert uow.receivables.get(receivable.id).outstanding_amount.to_string() == "50.00"
