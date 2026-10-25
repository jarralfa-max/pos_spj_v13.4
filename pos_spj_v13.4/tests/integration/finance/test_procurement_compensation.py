"""Auditoría Compras d9f2bca C12 — compensaciones financieras de Compras.

Una devolución confirmada aplica nota de crédito a la CxP de su factura (y el
exceso queda como anticipo del proveedor); el reverso de una compra de contado
revierte su asiento de pago.
"""

from datetime import date
from decimal import Decimal

from backend.application.event_handlers.finance.procurement_compensation_bridges import (
    ProcurementImmediatePaymentReversalHandler,
    ProcurementReturnCreditHandler,
)
from backend.application.services.finance.posting_engine import PostingEngine
from backend.application.use_cases.finance.create_payable_use_case import create_payable_in
from backend.domain.finance.enums import JournalType, PostingPurpose
from backend.domain.finance.services.journal_posting_service import LineSpec
from backend.domain.finance.value_objects.money import Money
from backend.domain.finance.value_objects.posting_reference import PostingReference
from backend.infrastructure.db.repositories.finance.unit_of_work import FinanceUnitOfWork
from backend.shared.ids import new_uuid
from tests.integration.finance.conftest import account_id

TODAY = date(2026, 7, 16)


def _balance(conn, code):
    rows = conn.execute(
        "SELECT jl.debit_amount, jl.credit_amount FROM journal_lines jl"
        " JOIN journal_entries je ON je.id=jl.journal_entry_id"
        " JOIN accounts a ON a.id=jl.account_id WHERE a.code=? AND je.status IN"
        " ('POSTED','REVERSED')", (code,)).fetchall()
    return sum((Decimal(d) - Decimal(c) for d, c in rows), Decimal("0"))


def _return_payload(**overrides):
    payload = {"document_id": new_uuid(), "operation_id": new_uuid(),
               "document_number": "DEV-1", "timestamp": "2026-07-16T12:00:00",
               "currency_code": "MXN", "return_value": "100.00", "return_tax": "16.00"}
    payload.update(overrides)
    return payload


def test_return_credit_reduces_the_invoice_payable(bootstrapped_conn):
    invoice_id = new_uuid()
    with FinanceUnitOfWork(bootstrapped_conn) as uow:
        payable = create_payable_in(
            uow, supplier_id=new_uuid(), amount="1160.00", currency_code="MXN",
            document_number="F-1", issue_date=TODAY, due_date=None, branch_id=None,
            source_module="procurement", source_document_id=invoice_id,
            operation_id=new_uuid())
    payload = _return_payload(invoice_ids=[invoice_id])
    handler = ProcurementReturnCreditHandler(bootstrapped_conn)
    handler.handle(payload)
    handler.handle(payload)          # reentrega: un solo efecto
    with FinanceUnitOfWork(bootstrapped_conn) as uow:
        stored = uow.payables.get(payable.id)
    assert stored.outstanding_amount.to_string() == "1044.00"
    assert _balance(bootstrapped_conn, "2101") == Decimal("116.00")      # Dr Proveedores
    assert _balance(bootstrapped_conn, "1150") == Decimal("-100.00")     # Cr Inventario
    assert _balance(bootstrapped_conn, "1170") == Decimal("-16.00")      # Cr IVA acreditable


def test_return_without_open_payable_becomes_supplier_advance(bootstrapped_conn):
    invoice_id = new_uuid()
    with FinanceUnitOfWork(bootstrapped_conn) as uow:
        payable = create_payable_in(
            uow, supplier_id=new_uuid(), amount="50.00", currency_code="MXN",
            document_number="F-2", issue_date=TODAY, due_date=None, branch_id=None,
            source_module="procurement", source_document_id=invoice_id,
            operation_id=new_uuid())
    ProcurementReturnCreditHandler(bootstrapped_conn).handle(
        _return_payload(invoice_ids=[invoice_id]))
    with FinanceUnitOfWork(bootstrapped_conn) as uow:
        assert uow.payables.get(payable.id).outstanding_amount.is_zero()
    assert _balance(bootstrapped_conn, "1140") == Decimal("66.00")       # anticipo


def test_uninvoiced_return_has_no_financial_entry(bootstrapped_conn):
    ProcurementReturnCreditHandler(bootstrapped_conn).handle(_return_payload(invoice_ids=[]))
    assert bootstrapped_conn.execute("SELECT COUNT(*) FROM journal_entries").fetchone()[0] == 0


def test_reversed_cash_purchase_reverses_its_payment_entry(bootstrapped_conn):
    document_id = new_uuid()
    with FinanceUnitOfWork(bootstrapped_conn) as uow:
        PostingEngine().post(
            uow, JournalType.PURCHASES, TODAY, "Compra de contado",
            PostingReference("procurement", document_id, PostingPurpose.SUPPLIER_PAYMENT,
                             new_uuid()),
            [LineSpec(account_id(bootstrapped_conn, "1150"), debit=Money.from_string("90")),
             LineSpec(account_id(bootstrapped_conn, "1110"), credit=Money.from_string("90"))])
    payload = {"document_id": document_id, "operation_id": new_uuid(),
               "timestamp": "2026-07-16T13:00:00", "reason": "Compra duplicada"}
    handler = ProcurementImmediatePaymentReversalHandler(bootstrapped_conn)
    handler.handle(payload)
    handler.handle(payload)
    assert _balance(bootstrapped_conn, "1110") == Decimal("0.00")
    assert _balance(bootstrapped_conn, "1150") == Decimal("0.00")
