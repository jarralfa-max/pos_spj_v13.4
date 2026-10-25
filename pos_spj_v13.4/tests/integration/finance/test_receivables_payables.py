"""FASES 7, 8 y 10 — CxC (cobro aplicado explícitamente) y CxP (ciclo segregado de pagos)."""

from datetime import date
from decimal import Decimal

import pytest

from backend.application.use_cases.finance.apply_collection_use_case import ApplyCollectionUseCase
from backend.application.use_cases.finance.authorize_supplier_payment_use_case import (
    AuthorizeSupplierPaymentUseCase,
)
from backend.application.use_cases.finance.create_payable_use_case import CreatePayableUseCase
from backend.application.use_cases.finance.create_receivable_use_case import (
    CreateReceivableUseCase,
)
from backend.application.use_cases.finance.execute_supplier_payment_use_case import (
    ExecuteSupplierPaymentUseCase,
)
from backend.application.use_cases.finance.finance_configuration_use_cases import (
    UpdateFinanceSettingsUseCase,
)
from backend.application.use_cases.finance.manage_payable_controls_use_case import (
    ManagePayableControlsUseCase,
)
from backend.application.use_cases.finance.manage_receivable_followup_use_case import (
    DisputeReceivableUseCase,
)
from backend.application.use_cases.finance.mark_overdue_documents_use_case import (
    MarkOverdueDocumentsUseCase,
)
from backend.application.use_cases.finance.register_collection_use_case import (
    RegisterCollectionUseCase,
)
from backend.application.use_cases.finance.schedule_supplier_payment_use_case import (
    ScheduleSupplierPaymentUseCase,
)
from backend.application.use_cases.finance.supplier_advance_use_cases import (
    ApplySupplierAdvanceUseCase,
    RegisterSupplierAdvanceUseCase,
)
from backend.application.use_cases.finance.write_off_receivable_use_case import (
    WriteOffReceivableUseCase,
)
from backend.domain.finance.enums import (
    CollectionStatus,
    PayableStatus,
    PurchaseDebitNature,
    ReceivableStatus,
    SupplierPaymentStatus,
    TreasuryAccountType,
)
from backend.domain.finance.exceptions import (
    CollectionAlreadyAppliedError,
    CollectionAmountExceededError,
    FinanceDomainError,
    InsufficientTreasuryFundsError,
    PaymentAlreadyExecutedError,
    PaymentAuthorizationError,
    PaymentNotAuthorizedError,
    SegregationOfDutiesError,
    SupplierDocumentBlockedError,
)
from backend.infrastructure.db.repositories.finance.unit_of_work import FinanceUnitOfWork
from backend.infrastructure.integrations.finance_supplier_directory import (
    SqliteSupplierDirectory,
)
from backend.shared.ids import new_uuid
from tests.integration.finance.conftest import account_id, fund, register_supplier, treasury

TODAY = date(2026, 7, 16)


def _bank(conn):
    return treasury(conn, TreasuryAccountType.BANK)


def _balance(conn, code: str) -> Decimal:
    rows = conn.execute(
        "SELECT jl.base_debit_amount, jl.base_credit_amount FROM journal_lines jl"
        " JOIN journal_entries je ON je.id = jl.journal_entry_id JOIN accounts a"
        " ON a.id = jl.account_id WHERE a.code=? AND je.status IN ('POSTED','REVERSED')",
        (code,)).fetchall()
    return sum((Decimal(d) - Decimal(c) for d, c in rows), Decimal("0"))


class TestCollections:
    def _receivable(self, conn, customer_id, amount="1000.00", number="F-100",
                    due_date=None):
        return CreateReceivableUseCase().execute(
            conn, customer_id=customer_id, amount=amount, document_number=number,
            issue_date=TODAY, due_date=due_date, operation_id=new_uuid(),
            counterpart_account_id=account_id(conn, "4101"))

    def test_partial_then_full_collection(self, bootstrapped_conn):
        customer = new_uuid()
        receivable = self._receivable(bootstrapped_conn, customer)
        uc = RegisterCollectionUseCase()
        uc.execute(bootstrapped_conn, customer_id=customer, amount="400.00",
                   treasury_account_id=_bank(bootstrapped_conn).id, collection_date=TODAY,
                   applications=[{"receivable_id": receivable.id, "amount": "400.00"}],
                   operation_id=new_uuid())
        with FinanceUnitOfWork(bootstrapped_conn) as uow:
            stored = uow.receivables.get(receivable.id)
        assert stored.status is ReceivableStatus.PARTIALLY_COLLECTED
        assert stored.outstanding_amount.to_string() == "600.00"
        uc.execute(bootstrapped_conn, customer_id=customer, amount="600.00",
                   treasury_account_id=_bank(bootstrapped_conn).id, collection_date=TODAY,
                   applications=[{"receivable_id": receivable.id, "amount": "600.00"}],
                   operation_id=new_uuid())
        with FinanceUnitOfWork(bootstrapped_conn) as uow:
            assert uow.receivables.get(receivable.id).status is ReceivableStatus.COLLECTED

    def test_one_collection_applied_to_several_documents(self, bootstrapped_conn):
        customer = new_uuid()
        first = self._receivable(bootstrapped_conn, customer, "300.00", "F-1")
        second = self._receivable(bootstrapped_conn, customer, "200.00", "F-2")
        collection = RegisterCollectionUseCase().execute(
            bootstrapped_conn, customer_id=customer, amount="500.00",
            treasury_account_id=_bank(bootstrapped_conn).id, collection_date=TODAY,
            applications=[{"receivable_id": first.id, "amount": "300.00"},
                          {"receivable_id": second.id, "amount": "200.00"}],
            operation_id=new_uuid())
        assert collection.status is CollectionStatus.APPLIED
        with FinanceUnitOfWork(bootstrapped_conn) as uow:
            assert uow.receivables.get(first.id).outstanding_amount.is_zero()
            assert uow.receivables.get(second.id).outstanding_amount.is_zero()
            assert len(uow.collections.list_applications(collection_id=collection.id)) == 2
        assert _balance(bootstrapped_conn, "1130") == Decimal("0")

    def test_registering_income_does_not_mark_receivable_collected(self, bootstrapped_conn):
        """Un cobro sin aplicación queda como saldo a favor: la CxC sigue abierta."""
        customer = new_uuid()
        receivable = self._receivable(bootstrapped_conn, customer, "100.00")
        collection = RegisterCollectionUseCase().execute(
            bootstrapped_conn, customer_id=customer, amount="100.00",
            treasury_account_id=_bank(bootstrapped_conn).id, collection_date=TODAY,
            operation_id=new_uuid())
        assert collection.status is CollectionStatus.UNAPPLIED
        with FinanceUnitOfWork(bootstrapped_conn) as uow:
            assert uow.receivables.get(receivable.id).status is ReceivableStatus.OPEN
        assert _balance(bootstrapped_conn, "2140") == Decimal("-100.00")   # anticipo
        ApplyCollectionUseCase().execute(
            bootstrapped_conn, collection_id=collection.id,
            applications=[{"receivable_id": receivable.id, "amount": "100.00"}],
            application_date=TODAY, operation_id=new_uuid(), applied_by="ana")
        with FinanceUnitOfWork(bootstrapped_conn) as uow:
            assert uow.receivables.get(receivable.id).status is ReceivableStatus.COLLECTED
        assert _balance(bootstrapped_conn, "2140") == Decimal("0")
        assert _balance(bootstrapped_conn, "1130") == Decimal("0")

    def test_over_collection_rejected(self, bootstrapped_conn):
        customer = new_uuid()
        receivable = self._receivable(bootstrapped_conn, customer, "100.00")
        with pytest.raises(CollectionAmountExceededError):
            RegisterCollectionUseCase().execute(
                bootstrapped_conn, customer_id=customer, amount="150.00",
                treasury_account_id=_bank(bootstrapped_conn).id, collection_date=TODAY,
                applications=[{"receivable_id": receivable.id, "amount": "150.00"}],
                operation_id=new_uuid())
        with pytest.raises(CollectionAmountExceededError):
            RegisterCollectionUseCase().execute(
                bootstrapped_conn, customer_id=customer, amount="50.00",
                treasury_account_id=_bank(bootstrapped_conn).id, collection_date=TODAY,
                applications=[{"receivable_id": receivable.id, "amount": "80.00"}],
                operation_id=new_uuid())

    def test_double_application_rejected(self, bootstrapped_conn):
        customer = new_uuid()
        receivable = self._receivable(bootstrapped_conn, customer, "100.00")
        collection = RegisterCollectionUseCase().execute(
            bootstrapped_conn, customer_id=customer, amount="100.00",
            treasury_account_id=_bank(bootstrapped_conn).id, collection_date=TODAY,
            operation_id=new_uuid())
        uc = ApplyCollectionUseCase()
        op = new_uuid()
        uc.execute(bootstrapped_conn, collection_id=collection.id,
                   applications=[{"receivable_id": receivable.id, "amount": "100.00"}],
                   application_date=TODAY, operation_id=op, applied_by="ana")
        # el mismo comando repetido no duplica
        uc.execute(bootstrapped_conn, collection_id=collection.id,
                   applications=[{"receivable_id": receivable.id, "amount": "100.00"}],
                   application_date=TODAY, operation_id=op, applied_by="ana")
        with pytest.raises(CollectionAlreadyAppliedError):
            uc.execute(bootstrapped_conn, collection_id=collection.id,
                       applications=[{"receivable_id": receivable.id, "amount": "50.00"}],
                       application_date=TODAY, operation_id=op, applied_by="ana")
        with pytest.raises(CollectionAmountExceededError):
            uc.execute(bootstrapped_conn, collection_id=collection.id,
                       applications=[{"receivable_id": receivable.id, "amount": "100.00"}],
                       application_date=TODAY, operation_id=new_uuid(), applied_by="ana")

    def test_collection_for_other_customer_rejected(self, bootstrapped_conn):
        receivable = self._receivable(bootstrapped_conn, new_uuid(), "100.00")
        with pytest.raises(FinanceDomainError):
            RegisterCollectionUseCase().execute(
                bootstrapped_conn, customer_id=new_uuid(), amount="100.00",
                treasury_account_id=_bank(bootstrapped_conn).id, collection_date=TODAY,
                applications=[{"receivable_id": receivable.id, "amount": "100.00"}],
                operation_id=new_uuid())

    def test_collection_idempotent_by_operation_id(self, bootstrapped_conn):
        customer = new_uuid()
        receivable = self._receivable(bootstrapped_conn, customer)
        op = new_uuid()
        kwargs = dict(customer_id=customer, amount="400.00",
                      treasury_account_id=_bank(bootstrapped_conn).id, collection_date=TODAY,
                      applications=[{"receivable_id": receivable.id, "amount": "400.00"}],
                      operation_id=op)
        uc = RegisterCollectionUseCase()
        assert uc.execute(bootstrapped_conn, **kwargs).id == \
            uc.execute(bootstrapped_conn, **kwargs).id
        with FinanceUnitOfWork(bootstrapped_conn) as uow:
            assert uow.receivables.get(receivable.id).outstanding_amount.to_string() == "600.00"

    def test_overdue_dispute_and_write_off(self, bootstrapped_conn):
        customer = new_uuid()
        receivable = self._receivable(bootstrapped_conn, customer, "250.00",
                                      due_date=date(2026, 7, 1))
        result = MarkOverdueDocumentsUseCase().execute(bootstrapped_conn, as_of=TODAY)
        assert result.receivables == 1
        assert MarkOverdueDocumentsUseCase().execute(bootstrapped_conn,
                                                     as_of=TODAY).receivables == 0
        with FinanceUnitOfWork(bootstrapped_conn) as uow:
            assert uow.receivables.get(receivable.id).status is ReceivableStatus.OVERDUE
        assert bootstrapped_conn.execute(
            "SELECT COUNT(*) FROM finance_outbox WHERE event_name='RECEIVABLE_OVERDUE'"
        ).fetchone()[0] == 1
        followup = DisputeReceivableUseCase()
        followup.open(bootstrapped_conn, receivable_id=receivable.id,
                      reason="Producto en mal estado", operation_id=new_uuid(),
                      disputed_by="ana")
        followup.resolve(bootstrapped_conn, receivable_id=receivable.id,
                         resolution="Se acordó pago", as_of=TODAY, operation_id=new_uuid(),
                         resolved_by="ana")
        WriteOffReceivableUseCase().execute(
            bootstrapped_conn, receivable_id=receivable.id, reason="Cliente no localizable",
            write_off_date=TODAY, operation_id=new_uuid(), authorized_by="beto")
        with FinanceUnitOfWork(bootstrapped_conn) as uow:
            stored = uow.receivables.get(receivable.id)
        assert stored.status is ReceivableStatus.WRITTEN_OFF
        assert stored.written_off_by == "beto"
        assert _balance(bootstrapped_conn, "6160") == Decimal("250.00")
        assert bootstrapped_conn.execute(
            "SELECT COUNT(*) FROM finance_audit_log WHERE action='RECEIVABLE_WRITTEN_OFF'"
            " AND reason='Cliente no localizable'").fetchone()[0] == 1


class TestSupplierPaymentLifecycle:
    def _payable(self, conn, amount="2000.00", **kwargs):
        return CreatePayableUseCase().execute(
            conn, supplier_id=kwargs.pop("supplier_id", None) or register_supplier(conn),
            amount=amount, document_number="FP-01", issue_date=TODAY, operation_id=new_uuid(),
            counterpart_account_id=account_id(conn, "6130"), **kwargs)

    def _flow(self, conn):
        directory = SqliteSupplierDirectory(conn)
        return (ScheduleSupplierPaymentUseCase(directory), AuthorizeSupplierPaymentUseCase(),
                ExecuteSupplierPaymentUseCase(directory))

    def test_full_segregated_lifecycle(self, bootstrapped_conn):
        payable = self._payable(bootstrapped_conn)
        bank = _bank(bootstrapped_conn)
        fund(bootstrapped_conn, bank.id, "5000.00")
        schedule, authorize, execute = self._flow(bootstrapped_conn)
        payment = schedule.execute(
            bootstrapped_conn, payable_id=payable.id, amount="2000.00", scheduled_date=TODAY,
            treasury_account_id=bank.id, scheduled_by="ana", operation_id=new_uuid())
        assert payment.status is SupplierPaymentStatus.SCHEDULED
        with FinanceUnitOfWork(bootstrapped_conn) as uow:
            assert uow.payables.get(payable.id).status is PayableStatus.SCHEDULED
        authorize.execute(bootstrapped_conn, payment_id=payment.id, authorized_by="beto",
                          operation_id=new_uuid())
        with FinanceUnitOfWork(bootstrapped_conn) as uow:
            assert uow.payables.get(payable.id).status is PayableStatus.AUTHORIZED
        execute.execute(bootstrapped_conn, payment_id=payment.id, executed_date=TODAY,
                        operation_id=new_uuid(), execution_reference="SPEI-0001",
                        executed_by="caro")
        with FinanceUnitOfWork(bootstrapped_conn) as uow:
            stored_payment = uow.supplier_payments.get(payment.id)
            stored_payable = uow.payables.get(payable.id)
        assert stored_payment.status is SupplierPaymentStatus.EXECUTED
        assert stored_payment.journal_entry_id is not None
        assert stored_payable.status is PayableStatus.PAID
        assert bootstrapped_conn.execute(
            "SELECT COUNT(*) FROM finance_outbox WHERE event_name='PAYABLE_SETTLED'"
        ).fetchone()[0] == 1

    def test_partial_payment(self, bootstrapped_conn):
        payable = self._payable(bootstrapped_conn)
        bank = _bank(bootstrapped_conn)
        fund(bootstrapped_conn, bank.id, "5000.00")
        schedule, authorize, execute = self._flow(bootstrapped_conn)
        payment = schedule.execute(
            bootstrapped_conn, payable_id=payable.id, amount="500.00", scheduled_date=TODAY,
            treasury_account_id=bank.id, scheduled_by="ana", operation_id=new_uuid())
        authorize.execute(bootstrapped_conn, payment_id=payment.id, authorized_by="beto",
                          operation_id=new_uuid())
        execute.execute(bootstrapped_conn, payment_id=payment.id, executed_date=TODAY,
                        operation_id=new_uuid(), execution_reference="SPEI-1",
                        executed_by="caro")
        with FinanceUnitOfWork(bootstrapped_conn) as uow:
            stored = uow.payables.get(payable.id)
        assert stored.status is PayableStatus.PARTIALLY_PAID
        assert stored.outstanding_amount.to_string() == "1500.00"

    def test_execution_without_authorization_fails(self, bootstrapped_conn):
        payable = self._payable(bootstrapped_conn)
        bank = _bank(bootstrapped_conn)
        schedule, _, execute = self._flow(bootstrapped_conn)
        payment = schedule.execute(
            bootstrapped_conn, payable_id=payable.id, amount="2000.00", scheduled_date=TODAY,
            treasury_account_id=bank.id, scheduled_by="ana", operation_id=new_uuid())
        with pytest.raises(PaymentNotAuthorizedError):
            execute.execute(bootstrapped_conn, payment_id=payment.id, executed_date=TODAY,
                            operation_id=new_uuid(), execution_reference="SPEI-1",
                            executed_by="caro")

    def test_scheduler_cannot_self_authorize(self, bootstrapped_conn):
        payable = self._payable(bootstrapped_conn)
        schedule, authorize, _ = self._flow(bootstrapped_conn)
        payment = schedule.execute(
            bootstrapped_conn, payable_id=payable.id, amount="500.00", scheduled_date=TODAY,
            treasury_account_id=_bank(bootstrapped_conn).id, scheduled_by="ana",
            operation_id=new_uuid())
        with pytest.raises((PaymentAuthorizationError, SegregationOfDutiesError)):
            authorize.execute(bootstrapped_conn, payment_id=payment.id, authorized_by="ana",
                              operation_id=new_uuid())

    def test_authorizer_cannot_execute_under_dual_control(self, bootstrapped_conn):
        payable = self._payable(bootstrapped_conn)
        bank = _bank(bootstrapped_conn)
        fund(bootstrapped_conn, bank.id, "5000.00")
        schedule, authorize, execute = self._flow(bootstrapped_conn)
        payment = schedule.execute(
            bootstrapped_conn, payable_id=payable.id, amount="100.00", scheduled_date=TODAY,
            treasury_account_id=bank.id, scheduled_by="ana", operation_id=new_uuid())
        authorize.execute(bootstrapped_conn, payment_id=payment.id, authorized_by="beto",
                          operation_id=new_uuid())
        with pytest.raises(SegregationOfDutiesError):
            execute.execute(bootstrapped_conn, payment_id=payment.id, executed_date=TODAY,
                            operation_id=new_uuid(), execution_reference="SPEI-1",
                            executed_by="beto")

    def test_second_authorization_over_threshold(self, bootstrapped_conn):
        UpdateFinanceSettingsUseCase().execute(
            bootstrapped_conn, changes={"payment_second_authorization_threshold": "1000"},
            operation_id=new_uuid(), updated_by="admin")
        payable = self._payable(bootstrapped_conn)
        bank = _bank(bootstrapped_conn)
        fund(bootstrapped_conn, bank.id, "5000.00")
        schedule, authorize, execute = self._flow(bootstrapped_conn)
        payment = schedule.execute(
            bootstrapped_conn, payable_id=payable.id, amount="2000.00", scheduled_date=TODAY,
            treasury_account_id=bank.id, scheduled_by="ana", operation_id=new_uuid())
        assert payment.second_authorization_required
        first = authorize.execute(bootstrapped_conn, payment_id=payment.id,
                                  authorized_by="beto", operation_id=new_uuid())
        assert first.status is SupplierPaymentStatus.SCHEDULED
        with pytest.raises(PaymentNotAuthorizedError):
            execute.execute(bootstrapped_conn, payment_id=payment.id, executed_date=TODAY,
                            operation_id=new_uuid(), execution_reference="SPEI-1",
                            executed_by="dani")
        with pytest.raises((PaymentAuthorizationError, SegregationOfDutiesError)):
            authorize.execute(bootstrapped_conn, payment_id=payment.id, authorized_by="beto",
                              operation_id=new_uuid())
        authorize.execute(bootstrapped_conn, payment_id=payment.id, authorized_by="caro",
                          operation_id=new_uuid())
        execute.execute(bootstrapped_conn, payment_id=payment.id, executed_date=TODAY,
                        operation_id=new_uuid(), execution_reference="SPEI-1",
                        executed_by="dani")
        with FinanceUnitOfWork(bootstrapped_conn) as uow:
            assert uow.supplier_payments.get(payment.id).status is SupplierPaymentStatus.EXECUTED

    def test_payment_without_funds_rejected(self, bootstrapped_conn):
        payable = self._payable(bootstrapped_conn)
        bank = _bank(bootstrapped_conn)
        schedule, authorize, execute = self._flow(bootstrapped_conn)
        payment = schedule.execute(
            bootstrapped_conn, payable_id=payable.id, amount="2000.00", scheduled_date=TODAY,
            treasury_account_id=bank.id, scheduled_by="ana", operation_id=new_uuid())
        authorize.execute(bootstrapped_conn, payment_id=payment.id, authorized_by="beto",
                          operation_id=new_uuid())
        with pytest.raises(InsufficientTreasuryFundsError):
            execute.execute(bootstrapped_conn, payment_id=payment.id, executed_date=TODAY,
                            operation_id=new_uuid(), execution_reference="SPEI-1",
                            executed_by="caro")

    def test_blocked_document_is_not_paid_until_unblocked(self, bootstrapped_conn):
        payable = self._payable(bootstrapped_conn)
        controls = ManagePayableControlsUseCase()
        controls.block(bootstrapped_conn, payable_id=payable.id,
                       reason="Recepción 10 kg menos que la factura", operation_id=new_uuid(),
                       actor="ana")
        schedule, _, _ = self._flow(bootstrapped_conn)
        with pytest.raises(SupplierDocumentBlockedError):
            schedule.execute(
                bootstrapped_conn, payable_id=payable.id, amount="100.00", scheduled_date=TODAY,
                treasury_account_id=_bank(bootstrapped_conn).id, scheduled_by="ana",
                operation_id=new_uuid())
        controls.unblock(bootstrapped_conn, payable_id=payable.id,
                         reason="Proveedor envió nota de crédito", operation_id=new_uuid(),
                         actor="beto")
        schedule.execute(
            bootstrapped_conn, payable_id=payable.id, amount="100.00", scheduled_date=TODAY,
            treasury_account_id=_bank(bootstrapped_conn).id, scheduled_by="ana",
            operation_id=new_uuid())

    def test_purchases_never_pay_from_pos_register(self, bootstrapped_conn):
        """Regla contable: las compras no salen de Caja POS."""
        from backend.domain.finance.entities.treasury_account import TreasuryAccount
        with FinanceUnitOfWork(bootstrapped_conn) as uow:
            register = TreasuryAccount.create(
                "Caja POS Sucursal", TreasuryAccountType.CASH_REGISTER,
                uow.accounts.get_by_code("1102").id)
            uow.treasury.save(register)
        payable = self._payable(bootstrapped_conn)
        schedule, _, _ = self._flow(bootstrapped_conn)
        with pytest.raises(FinanceDomainError, match="Caja POS"):
            schedule.execute(
                bootstrapped_conn, payable_id=payable.id, amount="100.00", scheduled_date=TODAY,
                treasury_account_id=register.id, scheduled_by="ana", operation_id=new_uuid())

    def test_double_execution_is_rejected_without_second_entry(self, bootstrapped_conn):
        payable = self._payable(bootstrapped_conn)
        bank = _bank(bootstrapped_conn)
        fund(bootstrapped_conn, bank.id, "5000.00")
        schedule, authorize, execute = self._flow(bootstrapped_conn)
        payment = schedule.execute(
            bootstrapped_conn, payable_id=payable.id, amount="2000.00", scheduled_date=TODAY,
            treasury_account_id=bank.id, scheduled_by="ana", operation_id=new_uuid())
        authorize.execute(bootstrapped_conn, payment_id=payment.id, authorized_by="beto",
                          operation_id=new_uuid())
        execute.execute(bootstrapped_conn, payment_id=payment.id, executed_date=TODAY,
                        operation_id=new_uuid(), execution_reference="SPEI-0001",
                        executed_by="caro")
        execute.execute(bootstrapped_conn, payment_id=payment.id, executed_date=TODAY,
                        operation_id=new_uuid(), execution_reference="SPEI-0001",
                        executed_by="caro")  # reintento de la misma ejecución
        assert bootstrapped_conn.execute(
            "SELECT COUNT(*) FROM journal_entries WHERE posting_purpose='SUPPLIER_PAYMENT'"
        ).fetchone()[0] == 1
        with FinanceUnitOfWork(bootstrapped_conn) as uow:
            payment_entity = uow.supplier_payments.get(payment.id)
        with pytest.raises(PaymentAlreadyExecutedError):
            payment_entity.execute(TODAY, "otro")

    def test_early_payment_discount_and_retention(self, bootstrapped_conn):
        payable = self._payable(bootstrapped_conn, amount="1000.00", retention_amount="100.00",
                                early_payment_discount_percent="2",
                                early_payment_discount_until=date(2026, 7, 20))
        assert payable.original_amount.to_string() == "900.00"
        assert _balance(bootstrapped_conn, "2155") == Decimal("-100.00")
        bank = _bank(bootstrapped_conn)
        fund(bootstrapped_conn, bank.id, "5000.00")
        schedule, authorize, execute = self._flow(bootstrapped_conn)
        payment = schedule.execute(
            bootstrapped_conn, payable_id=payable.id, amount="882.00", scheduled_date=TODAY,
            treasury_account_id=bank.id, scheduled_by="ana", operation_id=new_uuid())
        authorize.execute(bootstrapped_conn, payment_id=payment.id, authorized_by="beto",
                          operation_id=new_uuid())
        execute.execute(bootstrapped_conn, payment_id=payment.id, executed_date=TODAY,
                        operation_id=new_uuid(), execution_reference="SPEI-9",
                        executed_by="caro")
        with FinanceUnitOfWork(bootstrapped_conn) as uow:
            stored = uow.payables.get(payable.id)
        assert stored.outstanding_amount.to_string() == "0.36"   # 900 − 882 − 17.64
        assert _balance(bootstrapped_conn, "7130") == Decimal("-17.64")

    def test_supplier_advance_then_applied(self, bootstrapped_conn):
        supplier = register_supplier(bootstrapped_conn)
        bank = _bank(bootstrapped_conn)
        fund(bootstrapped_conn, bank.id, "1000.00")
        advance = RegisterSupplierAdvanceUseCase(SqliteSupplierDirectory(bootstrapped_conn)) \
            .execute(bootstrapped_conn, supplier_id=supplier, amount="300.00",
                     treasury_account_id=bank.id, advance_date=TODAY,
                     execution_reference="SPEI-A1", operation_id=new_uuid(), created_by="ana")
        assert _balance(bootstrapped_conn, "1140") == Decimal("300.00")
        payable = self._payable(bootstrapped_conn, amount="500.00", supplier_id=supplier)
        ApplySupplierAdvanceUseCase().execute(
            bootstrapped_conn, supplier_advance_id=advance.id, payable_id=payable.id,
            amount="300.00", application_date=TODAY, operation_id=new_uuid(),
            applied_by="beto")
        with FinanceUnitOfWork(bootstrapped_conn) as uow:
            assert uow.payables.get(payable.id).outstanding_amount.to_string() == "200.00"
        assert _balance(bootstrapped_conn, "1140") == Decimal("0")

    def test_finance_payable_requires_nature_or_account(self, bootstrapped_conn):
        with pytest.raises(FinanceDomainError):
            CreatePayableUseCase().execute(
                bootstrapped_conn, supplier_id=register_supplier(bootstrapped_conn),
                amount="10.00", document_number="X", issue_date=TODAY, operation_id=new_uuid())
        payable = CreatePayableUseCase().execute(
            bootstrapped_conn, supplier_id=register_supplier(bootstrapped_conn),
            amount="10.00", document_number="X2", issue_date=TODAY, operation_id=new_uuid(),
            debit_nature=PurchaseDebitNature.OPERATING_EXPENSE)
        assert payable.debit_nature is PurchaseDebitNature.OPERATING_EXPENSE
        assert _balance(bootstrapped_conn, "6130") == Decimal("10.00")
