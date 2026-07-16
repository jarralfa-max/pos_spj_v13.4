"""FASES 7-8 — CxC (cobros) y CxP (ciclo segregado de pagos)."""

from datetime import date

import pytest

from backend.application.use_cases.finance.payable_use_cases import (
    AuthorizeSupplierPaymentUseCase,
    CreatePayableUseCase,
    ExecuteSupplierPaymentUseCase,
    ScheduleSupplierPaymentUseCase,
)
from backend.application.use_cases.finance.receivable_use_cases import (
    CreateReceivableUseCase,
    RegisterCollectionUseCase,
)
from backend.domain.finance.enums import (
    PayableStatus,
    ReceivableStatus,
    SupplierPaymentStatus,
    TreasuryAccountType,
)
from backend.domain.finance.exceptions import (
    FinanceDomainError,
    InsufficientOutstandingError,
    PaymentAuthorizationError,
)
from backend.infrastructure.db.repositories.finance.unit_of_work import FinanceUnitOfWork
from backend.shared.ids import new_uuid

TODAY = date(2026, 7, 16)


def _treasury(conn, account_type=None):
    with FinanceUnitOfWork(conn) as uow:
        accounts = uow.treasury.list_active()
    if account_type:
        return next(a for a in accounts if a.account_type is account_type)
    return next(a for a in accounts if a.account_type is TreasuryAccountType.BANK)


class TestCollections:
    def _receivable(self, conn, amount="1000.00"):
        return CreateReceivableUseCase().execute(
            conn, customer_id=new_uuid(), amount=amount, document_number="F-100",
            issue_date=TODAY, operation_id=new_uuid(),
        )

    def test_partial_then_full_collection(self, bootstrapped_conn):
        receivable = self._receivable(bootstrapped_conn)
        bank = _treasury(bootstrapped_conn)
        uc = RegisterCollectionUseCase()
        uc.execute(bootstrapped_conn, receivable_id=receivable.id, amount="400.00",
                   treasury_account_id=bank.id, collection_date=TODAY,
                   operation_id=new_uuid())
        with FinanceUnitOfWork(bootstrapped_conn) as uow:
            stored = uow.receivables.get(receivable.id)
        assert stored.status is ReceivableStatus.PARTIALLY_COLLECTED
        assert stored.outstanding_amount.to_string() == "600.00"

        uc.execute(bootstrapped_conn, receivable_id=receivable.id, amount="600.00",
                   treasury_account_id=bank.id, collection_date=TODAY,
                   operation_id=new_uuid())
        with FinanceUnitOfWork(bootstrapped_conn) as uow:
            stored = uow.receivables.get(receivable.id)
        assert stored.status is ReceivableStatus.SETTLED

    def test_over_collection_rejected(self, bootstrapped_conn):
        receivable = self._receivable(bootstrapped_conn, amount="100.00")
        bank = _treasury(bootstrapped_conn)
        with pytest.raises(InsufficientOutstandingError):
            RegisterCollectionUseCase().execute(
                bootstrapped_conn, receivable_id=receivable.id, amount="150.00",
                treasury_account_id=bank.id, collection_date=TODAY,
                operation_id=new_uuid())

    def test_collection_idempotent_by_operation_id(self, bootstrapped_conn):
        receivable = self._receivable(bootstrapped_conn)
        bank = _treasury(bootstrapped_conn)
        op = new_uuid()
        uc = RegisterCollectionUseCase()
        first = uc.execute(bootstrapped_conn, receivable_id=receivable.id, amount="400.00",
                           treasury_account_id=bank.id, collection_date=TODAY,
                           operation_id=op)
        second = uc.execute(bootstrapped_conn, receivable_id=receivable.id, amount="400.00",
                            treasury_account_id=bank.id, collection_date=TODAY,
                            operation_id=op)
        assert first == second
        with FinanceUnitOfWork(bootstrapped_conn) as uow:
            stored = uow.receivables.get(receivable.id)
        assert stored.outstanding_amount.to_string() == "600.00"  # only one applied


class TestSupplierPaymentLifecycle:
    def _payable(self, conn, amount="2000.00"):
        return CreatePayableUseCase().execute(
            conn, supplier_id=new_uuid(), amount=amount, document_number="FP-01",
            issue_date=TODAY, operation_id=new_uuid(),
        )

    def test_full_segregated_lifecycle(self, bootstrapped_conn):
        payable = self._payable(bootstrapped_conn)
        bank = _treasury(bootstrapped_conn)
        scheduler, authorizer = new_uuid(), new_uuid()

        payment = ScheduleSupplierPaymentUseCase().execute(
            bootstrapped_conn, payable_id=payable.id, amount="2000.00",
            scheduled_date=TODAY, treasury_account_id=bank.id,
            scheduled_by=scheduler, operation_id=new_uuid())
        assert payment.status is SupplierPaymentStatus.SCHEDULED

        AuthorizeSupplierPaymentUseCase().execute(
            bootstrapped_conn, payment_id=payment.id, authorized_by=authorizer,
            operation_id=new_uuid())
        ExecuteSupplierPaymentUseCase().execute(
            bootstrapped_conn, payment_id=payment.id, executed_date=TODAY,
            operation_id=new_uuid())
        with FinanceUnitOfWork(bootstrapped_conn) as uow:
            stored_payment = uow.supplier_payments.get(payment.id)
            stored_payable = uow.payables.get(payable.id)
        assert stored_payment.status is SupplierPaymentStatus.EXECUTED
        assert stored_payment.journal_entry_id is not None
        assert stored_payable.status is PayableStatus.SETTLED

    def test_execution_without_authorization_fails(self, bootstrapped_conn):
        payable = self._payable(bootstrapped_conn)
        bank = _treasury(bootstrapped_conn)
        payment = ScheduleSupplierPaymentUseCase().execute(
            bootstrapped_conn, payable_id=payable.id, amount="2000.00",
            scheduled_date=TODAY, treasury_account_id=bank.id,
            scheduled_by=new_uuid(), operation_id=new_uuid())
        with pytest.raises(PaymentAuthorizationError):
            ExecuteSupplierPaymentUseCase().execute(
                bootstrapped_conn, payment_id=payment.id, executed_date=TODAY,
                operation_id=new_uuid())

    def test_scheduler_cannot_self_authorize(self, bootstrapped_conn):
        payable = self._payable(bootstrapped_conn)
        bank = _treasury(bootstrapped_conn)
        user = new_uuid()
        payment = ScheduleSupplierPaymentUseCase().execute(
            bootstrapped_conn, payable_id=payable.id, amount="500.00",
            scheduled_date=TODAY, treasury_account_id=bank.id,
            scheduled_by=user, operation_id=new_uuid())
        with pytest.raises(PaymentAuthorizationError):
            AuthorizeSupplierPaymentUseCase().execute(
                bootstrapped_conn, payment_id=payment.id, authorized_by=user,
                operation_id=new_uuid())

    def test_purchases_never_pay_from_pos_register(self, bootstrapped_conn):
        """Regla contable: las compras no salen de Caja POS."""
        from backend.domain.finance.entities.treasury_account import TreasuryAccount
        with FinanceUnitOfWork(bootstrapped_conn) as uow:
            ledger = uow.accounts.get_by_code("1102")
            register = TreasuryAccount.create(
                "Caja POS Sucursal", TreasuryAccountType.CASH_REGISTER, ledger.id)
            uow.treasury.save(register)
        payable = self._payable(bootstrapped_conn)
        with pytest.raises(FinanceDomainError, match="Caja POS"):
            ScheduleSupplierPaymentUseCase().execute(
                bootstrapped_conn, payable_id=payable.id, amount="100.00",
                scheduled_date=TODAY, treasury_account_id=register.id,
                scheduled_by=new_uuid(), operation_id=new_uuid())

    def test_double_execution_is_idempotent(self, bootstrapped_conn):
        payable = self._payable(bootstrapped_conn)
        bank = _treasury(bootstrapped_conn)
        payment = ScheduleSupplierPaymentUseCase().execute(
            bootstrapped_conn, payable_id=payable.id, amount="2000.00",
            scheduled_date=TODAY, treasury_account_id=bank.id,
            scheduled_by=new_uuid(), operation_id=new_uuid())
        AuthorizeSupplierPaymentUseCase().execute(
            bootstrapped_conn, payment_id=payment.id, authorized_by=new_uuid(),
            operation_id=new_uuid())
        uc = ExecuteSupplierPaymentUseCase()
        uc.execute(bootstrapped_conn, payment_id=payment.id, executed_date=TODAY,
                   operation_id=new_uuid())
        uc.execute(bootstrapped_conn, payment_id=payment.id, executed_date=TODAY,
                   operation_id=new_uuid())  # retry
        count = bootstrapped_conn.execute(
            "SELECT COUNT(*) FROM journal_entries WHERE posting_purpose='SUPPLIER_PAYMENT'"
        ).fetchone()[0]
        assert count == 1
