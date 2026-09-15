"""Fase 4 (§11) — a contado direct purchase used to leave NO financial trace.

`ConfirmDirectPurchaseUseCase` correctly emits `PURCHASE_PAYMENT_REQUESTED`
for an immediate-payment purchase and deliberately never books a CxP for it
(credit purchases get a CxP only later, through supplier-invoice matching —
see `test_integrations.py::test_payable_created_reaches_finance_and_creates_
real_payable`). But until `ProcurementImmediatePaymentBridgeHandler`, nothing
ever subscribed the derived `SUPPLIER_PAYMENT_SCHEDULED` event either — the
money left the business and nothing recorded it. This proves the real,
wired chain end-to-end: direct purchase confirm -> outbox dispatch ->
translator -> bridge handler -> a real, balanced journal entry against the
correct treasury account.
"""

from __future__ import annotations

import sqlite3

from backend.application.event_handlers.finance.procurement_immediate_payment_bridge import (
    ProcurementImmediatePaymentBridgeHandler,
)
from backend.application.procurement.integrations.procurement_outbox_dispatcher import (
    dispatch_procurement_outbox,
)
from backend.application.procurement.integrations.wiring import wire_procurement
from backend.application.procurement.use_cases.direct_purchase_use_cases import (
    ConfirmDirectPurchaseUseCase,
    CreateDirectPurchaseUseCase,
)
from backend.application.services.finance.finance_bootstrap import bootstrap_finance
from backend.domain.finance.enums import PostingPurpose
from backend.infrastructure.db.repositories.finance.unit_of_work import FinanceUnitOfWork
from backend.infrastructure.db.schema.document_output_schema import (
    create_document_numbering_schema,
)
from backend.infrastructure.db.schema.finance_schema import create_finance_schema
from backend.infrastructure.db.schema.procurement_schema import create_procurement_schema


class Bus:
    def __init__(self):
        self._subs = {}

    def publish(self, name, payload, async_=False):
        for fn in self._subs.get(name, []):
            fn(payload)

    def subscribe(self, name, handler, priority=50, label=""):
        self._subs.setdefault(name, []).append(handler)


def _conn():
    conn = sqlite3.connect(":memory:")
    conn.execute("PRAGMA foreign_keys = ON")
    create_procurement_schema(conn)
    create_document_numbering_schema(conn)
    create_finance_schema(conn)
    bootstrap_finance(conn)
    conn.execute("CREATE TABLE proveedores(id TEXT PRIMARY KEY, nombre TEXT, activo INTEGER,"
                " compras_habilitadas INTEGER, bloqueado_financiero INTEGER)")
    conn.execute("INSERT INTO proveedores VALUES ('s1','Proveedor Uno',1,1,0)")
    conn.commit()
    return conn


def _confirm_immediate_purchase(conn, *, payment_source: str):
    bus = Bus()
    wire_procurement(bus, conn)
    bus.subscribe("SUPPLIER_PAYMENT_SCHEDULED",
                  ProcurementImmediatePaymentBridgeHandler(conn).handle)

    created = CreateDirectPurchaseUseCase().execute(
        conn, actor_user_id="u1", operation_id="op-create", supplier_id="s1",
        branch_id="br-1", warehouse_id="wh-1",
        lines=[{"product_id": "p1", "description": "Pollo", "quantity": "10",
                "unit_cost": "30"}])
    assert created.success, created.message

    confirmed = ConfirmDirectPurchaseUseCase().execute(
        conn, actor_user_id="u1", direct_purchase_id=created.entity_id,
        operation_id="op-confirm", payment_source=payment_source)
    assert confirmed.success, confirmed.message

    dispatch_procurement_outbox(conn, bus)
    return created.entity_id


def test_bank_transfer_posts_a_balanced_journal_entry_to_the_bank_account():
    conn = _conn()
    document_id = _confirm_immediate_purchase(conn, payment_source="BANK_TRANSFER")

    with FinanceUnitOfWork(conn) as uow:
        bank = next(a for a in uow.treasury.list_active() if a.name == "Banco principal")
        entry = uow.journal_entries.find_by_posting_reference(
            "procurement", document_id, PostingPurpose.SUPPLIER_PAYMENT)

    assert entry is not None
    credited_bank = [ln for ln in entry.lines
                     if ln.account_id == bank.ledger_account_id and ln.credit]
    assert credited_bank, "the bank treasury account was not credited"
    assert sum(ln.credit.amount for ln in credited_bank) == sum(
        ln.debit.amount for ln in entry.lines if ln.debit)


def test_petty_cash_with_no_matching_treasury_account_is_skipped_not_guessed():
    """`bootstrap_finance` seeds GENERAL_CASH/BANK/PAYMENT_PROCESSOR — no
    PETTY_CASH account exists, so this must skip cleanly, not crash or post
    against the wrong account."""
    conn = _conn()
    document_id = _confirm_immediate_purchase(conn, payment_source="PETTY_CASH")

    with FinanceUnitOfWork(conn) as uow:
        entry = uow.journal_entries.find_by_posting_reference(
            "procurement", document_id, PostingPurpose.SUPPLIER_PAYMENT)

    assert entry is None


def test_ambiguous_payment_source_is_skipped_not_guessed():
    """TREASURY_ACCOUNT has no unambiguous TreasuryAccountType mapping by
    design (see the handler's own module docstring) — must never guess."""
    conn = _conn()
    document_id = _confirm_immediate_purchase(conn, payment_source="TREASURY_ACCOUNT")

    with FinanceUnitOfWork(conn) as uow:
        entry = uow.journal_entries.find_by_posting_reference(
            "procurement", document_id, PostingPurpose.SUPPLIER_PAYMENT)

    assert entry is None


def test_pos_cash_never_reaches_the_handler_at_all():
    """Defense in depth: `downstream_translators.py` already rejects POS
    cash sources before publishing SUPPLIER_PAYMENT_SCHEDULED."""
    conn = _conn()
    bus = Bus()
    wire_procurement(bus, conn)
    bus.subscribe("SUPPLIER_PAYMENT_SCHEDULED",
                  ProcurementImmediatePaymentBridgeHandler(conn).handle)

    created = CreateDirectPurchaseUseCase().execute(
        conn, actor_user_id="u1", operation_id="op-create-2", supplier_id="s1",
        branch_id="br-1", warehouse_id="wh-1",
        lines=[{"product_id": "p1", "description": "Pollo", "quantity": "10",
                "unit_cost": "30"}])
    assert created.success, created.message

    confirmed = ConfirmDirectPurchaseUseCase().execute(
        conn, actor_user_id="u1", direct_purchase_id=created.entity_id,
        operation_id="op-confirm-2", payment_source="POS_CASH")
    assert not confirmed.success
    assert confirmed.error_code == "INVALID_PAYMENT_SOURCE"
