"""PUR-11 — procurement integrations: inbound needs → requisitions, outbound
receipts → inventory, payables → CxP, immediate payment → treasury (never POS
cash), receipts → supplier performance, and the outbox → bus dispatch."""

import json
import sqlite3
from decimal import Decimal
from uuid import UUID

import pytest

from backend.application.procurement.integrations.procurement_outbox_dispatcher import (
    dispatch_procurement_outbox,
)
from backend.application.procurement.authorization import PurchaseAuthorizationPolicy
from backend.application.procurement.integrations.replenishment_intake import (
    ReplenishmentIntakeHandler,
)
from backend.application.procurement.integrations.wiring import wire_procurement
from backend.application.procurement.use_cases.direct_purchase_use_cases import (
    ConfirmDirectPurchaseUseCase,
    CreateDirectPurchaseUseCase,
)
from backend.application.procurement.use_cases.requisition_use_cases import (
    CreatePurchaseRequisitionUseCase,
)
from backend.domain.procurement.events import ReplenishmentNeedEvents


class FakeBus:
    def __init__(self):
        self.published: list[tuple[str, dict]] = []
        self._subs: dict[str, list] = {}

    def publish(self, event_name, payload, async_=False):
        self.published.append((event_name, payload))
        for fn in self._subs.get(event_name, []):
            fn(payload)

    def subscribe(self, event_name, handler, priority=50, label=""):
        self._subs.setdefault(event_name, []).append(handler)

    def names(self):
        return [n for n, _ in self.published]


class AllowAllPermissions:
    def has_permission(self, user_id, permission_code):
        return True


def authorized():
    return PurchaseAuthorizationPolicy(AllowAllPermissions())


# ── inbound: needs → requisitions ────────────────────────────────────────────
def test_replenishment_need_creates_requisition(proc_conn):
    handler = ReplenishmentIntakeHandler(
        proc_conn, use_case=CreatePurchaseRequisitionUseCase(authorized()))
    out = handler.handle({
        "event_id": "need-1", "event_name": ReplenishmentNeedEvents.STOCK_REPLENISHMENT_REQUIRED,
        "branch_id": "br-1", "requested_by_user_id": "u1",
        "product_id": "p1", "quantity": "12"})
    assert out["success"] and out["requisition_id"]
    rows = proc_conn.execute("SELECT COUNT(*) FROM purchase_requisitions").fetchone()[0]
    assert rows == 1


def test_replenishment_intake_is_idempotent(proc_conn):
    handler = ReplenishmentIntakeHandler(
        proc_conn, use_case=CreatePurchaseRequisitionUseCase(authorized()))
    payload = {"event_id": "need-x", "branch_id": "br-1", "requested_by_user_id": "u1",
               "lines": [{"product_id": "p1", "quantity": "5"}]}
    a = handler.handle(payload)
    b = handler.handle(payload)
    assert a["requisition_id"] == b["requisition_id"]
    assert proc_conn.execute("SELECT COUNT(*) FROM purchase_requisitions").fetchone()[0] == 1


# ── outbound translators via wiring ──────────────────────────────────────────
def test_receipt_event_translates_to_inventory_and_supplier(proc_conn):
    bus = FakeBus()
    wire_procurement(bus, proc_conn)
    bus.publish("GOODS_RECEIPT_COMPLETED", {
        "event_id": "e1", "operation_id": "op1", "supplier_id": "s1", "branch_id": "br-1",
        "warehouse_id": "wh-1", "purchase_order_id": "po-1",
        "inventory_lines": [{"product_id": "p1", "quantity": "8"}]})
    names = bus.names()
    assert "PURCHASE_STOCK_ENTRY_REGISTERED" in names
    assert "SUPPLIER_PERFORMANCE_RECORDED" in names
    inv = next(p for n, p in bus.published if n == "PURCHASE_STOCK_ENTRY_REGISTERED")
    assert inv["reason"] == "PURCHASE_RECEIPT"
    assert inv["lines"][0]["quantity"] == "8"
    assert UUID(inv["event_id"]).version == 7
    assert inv["causation_id"] == "e1"
    assert inv["correlation_id"] == "e1"


def test_translator_failure_propagates_so_source_is_not_acknowledged(proc_conn):
    class FailingBus(FakeBus):
        def publish(self, event_name, payload, async_=False):
            if event_name == "PURCHASE_STOCK_ENTRY_REGISTERED":
                raise RuntimeError("inventory unavailable")
            super().publish(event_name, payload, async_=async_)

    bus = FailingBus()
    wire_procurement(bus, proc_conn)
    with pytest.raises(RuntimeError, match="inventory unavailable"):
        bus.publish("GOODS_RECEIPT_COMPLETED", {
            "event_id": "e-fail", "operation_id": "op-fail",
            "inventory_lines": [{"product_id": "p1", "quantity": "1"}],
        })


def test_payable_event_translates_to_cxp(proc_conn):
    bus = FakeBus()
    wire_procurement(bus, proc_conn)
    bus.publish("ACCOUNT_PAYABLE_CREATE_REQUESTED", {
        "event_id": "e2", "operation_id": "op2", "supplier_id": "s1", "amount": "1000"})
    assert "PAYABLE_CREATED" in bus.names()


# ── PAYABLE_CREATED actually creates a real CxP (PUR-14 regression) ──────────
def test_payable_created_reaches_finance_and_creates_real_payable():
    """Before this fix, PAYABLE_CREATED had no subscriber anywhere in production
    wiring: CreatePayableUseCase existed and was fully tested in isolation, but a
    matched supplier invoice never produced an actual Payable/FinancialDocument."""
    from backend.application.event_handlers.finance.procurement_payable_bridge import (
        ProcurementPayableBridgeHandler,
    )
    from backend.application.services.finance.finance_bootstrap import bootstrap_finance
    from backend.domain.finance.enums import PostingPurpose
    from backend.infrastructure.db.repositories.finance.unit_of_work import (
        FinanceUnitOfWork,
    )
    from backend.infrastructure.db.schema.finance_schema import create_finance_schema
    from backend.infrastructure.db.schema.procurement_schema import create_procurement_schema

    conn = sqlite3.connect(":memory:")
    conn.execute("PRAGMA foreign_keys = ON")
    create_procurement_schema(conn)
    create_finance_schema(conn)
    bootstrap_finance(conn)
    conn.execute("CREATE TABLE proveedores(id TEXT PRIMARY KEY, nombre TEXT, activo INTEGER,"
                " compras_habilitadas INTEGER, bloqueado_financiero INTEGER)")
    conn.execute("INSERT INTO proveedores VALUES ('s1','Proveedor Uno',1,1,0)")

    bus = FakeBus()
    wire_procurement(bus, conn)
    bus.subscribe("PAYABLE_CREATED", ProcurementPayableBridgeHandler(conn).handle)

    from backend.application.procurement.use_cases.purchase_order_use_cases import (
        ApprovePurchaseOrderUseCase, CreatePurchaseOrderUseCase,
        ReceivePurchaseOrderUseCase, SendPurchaseOrderUseCase,
    )
    po = CreatePurchaseOrderUseCase(authorized()).execute(
        conn, actor_user_id="buyer", operation_id="po-fin-1", supplier_id="s1",
        branch_id="br-1", warehouse_id="wh-1",
        lines=[{"product_id": "p1", "description": "x", "quantity": "10", "unit_price": "100"}])
    assert po.success
    ApprovePurchaseOrderUseCase(authorized()).execute(
        conn, approver_user_id="jefe", purchase_order_id=po.entity_id, operation_id="po-fin-a")
    SendPurchaseOrderUseCase(authorized()).execute(
        conn, actor_user_id="buyer", purchase_order_id=po.entity_id, operation_id="po-fin-s")
    ReceivePurchaseOrderUseCase(authorized()).execute(
        conn, actor_user_id="alm", purchase_order_id=po.entity_id, operation_id="po-fin-r",
        receipt_lines=[{"product_id": "p1", "received_quantity": "10",
                        "accepted_quantity": "10"}])

    from backend.application.procurement.use_cases.supplier_invoice_use_cases import (
        CaptureSupplierInvoiceUseCase, MatchSupplierInvoiceUseCase,
    )
    po_line_id = conn.execute(
        "SELECT id FROM purchase_order_lines WHERE purchase_order_id=?",
        (po.entity_id,)).fetchone()[0]
    inv = CaptureSupplierInvoiceUseCase(authorized()).execute(
        conn, actor_user_id="cxp", operation_id="inv-fin-1", supplier_id="s1",
        invoice_number="FIN-1", total="1000", purchase_order_id=po.entity_id,
        lines=[{"product_id": "p1", "invoiced_quantity": "10", "unit_price": "100",
                "purchase_order_line_id": po_line_id}])
    assert inv.success

    dispatch_procurement_outbox(conn, bus)  # invoice capture's own outbox rows

    matched = MatchSupplierInvoiceUseCase(authorized()).execute(
        conn, actor_user_id="cxp", operation_id="inv-fin-match", invoice_id=inv.entity_id)
    assert matched.data["match_result"] == "MATCHED"

    summary = dispatch_procurement_outbox(conn, bus)
    assert summary["failed"] == 0, "silently-swallowed handler exception (check outbox log)"
    assert summary["dispatched"] >= 1
    assert "PAYABLE_CREATED" in bus.names()

    with FinanceUnitOfWork(conn) as uow:
        payable = uow.payables.find_by_operation_id("inv-fin-match")
    assert payable is not None
    assert payable.supplier_id == "s1"
    assert payable.original_amount.amount == Decimal("1000")
    assert payable.branch_id == "br-1"

    # recognition entry: Debit Inventario (INVENTORY is the line default) /
    # Credit CxP — this is the balanced journal entry CLAUDE.md §11 requires
    # for recognizing the liability, previously missing entirely (see
    # MIGRATION_LOG.md, Fase 5).
    with FinanceUnitOfWork(conn) as uow:
        entry = uow.journal_entries.find_by_posting_reference(
            "procurement", inv.entity_id, PostingPurpose.SUPPLIER_INVOICE)
    assert entry is not None
    assert entry.is_balanced()
    assert entry.total_credits().to_string() == "1000.00"

    # a second dispatch pass (retry/replay) must not create a duplicate payable
    dispatch_procurement_outbox(conn, bus)
    with FinanceUnitOfWork(conn) as uow:
        count = conn.execute(
            "SELECT COUNT(*) FROM payables WHERE operation_id=?", ("inv-fin-match",)
        ).fetchone()[0]
    assert count == 1
    conn.close()


def test_payable_recognition_entry_routes_by_purchase_nature_and_splits_tax():
    """A mixed invoice (some INVENTORY lines, some EXPENSE lines) must debit two
    different accounts, not dump everything into Inventario."""
    from backend.application.event_handlers.finance.procurement_payable_bridge import (
        ProcurementPayableBridgeHandler,
    )
    from datetime import date

    from backend.application.services.finance.finance_bootstrap import bootstrap_finance
    from backend.domain.finance.enums import PostingPurpose
    from backend.infrastructure.db.repositories.finance.unit_of_work import FinanceUnitOfWork
    from backend.infrastructure.db.schema.finance_schema import create_finance_schema

    conn = sqlite3.connect(":memory:")
    conn.execute("PRAGMA foreign_keys = ON")
    create_finance_schema(conn)
    bootstrap_finance(conn)

    ProcurementPayableBridgeHandler(conn).handle({
        "source_module": "procurement", "supplier_id": "s1", "document_number": "FPR-MIX-1",
        "document_id": "inv-mix-1", "amount": "1000", "currency_code": "MXN",
        "operation_id": "op-mix-1", "branch_id": "br-1",
        "nature_subtotals": {"INVENTORY": "600", "EXPENSE": "300"}, "tax_total": "100",
    })

    with FinanceUnitOfWork(conn) as uow:
        profile = uow.posting_profiles.find_effective("PURCHASE", date.today())
        entry = uow.journal_entries.find_by_posting_reference(
            "procurement", "inv-mix-1", PostingPurpose.SUPPLIER_INVOICE)
    assert entry is not None
    assert entry.is_balanced()
    assert entry.total_credits().to_string() == "1000.00"
    by_account = {line.account_id: line.debit.to_string() for line in entry.lines
                 if line.debit.is_positive()}
    assert by_account[profile.account_for("inventory_account_id")] == "600.00"
    assert by_account[profile.account_for("expense_account_id")] == "300.00"
    assert by_account[profile.account_for("tax_account_id")] == "100.00"
    conn.close()


def test_immediate_payment_never_from_pos_cash(proc_conn):
    bus = FakeBus()
    wire_procurement(bus, proc_conn)
    bus.publish("PURCHASE_PAYMENT_REQUESTED", {
        "event_id": "e3", "operation_id": "op3", "supplier_id": "s1", "amount": "500",
        "payment_source": "POS_CASH"})
    assert "SUPPLIER_PAYMENT_SCHEDULED" not in bus.names()
    bus.publish("PURCHASE_PAYMENT_REQUESTED", {
        "event_id": "e4", "operation_id": "op4", "supplier_id": "s1", "amount": "500",
        "payment_source": "PETTY_CASH"})
    scheduled = next(p for n, p in bus.published if n == "SUPPLIER_PAYMENT_SCHEDULED")
    assert scheduled["payment_source"] == "PETTY_CASH" and scheduled["immediate"] is True


# ── end-to-end: use case → outbox → dispatch → translators ───────────────────
def test_direct_purchase_outbox_dispatch_reaches_downstream(proc_conn):
    bus = FakeBus()
    wire_procurement(bus, proc_conn)

    created = CreateDirectPurchaseUseCase(authorized()).execute(
        proc_conn, actor_user_id="u1", operation_id="dp-op", supplier_id="s1",
        branch_id="br-1", warehouse_id="wh-1",
        lines=[{"product_id": "p1", "description": "Pollo", "quantity": "3",
                "unit_cost": "100", "tax": "48"}])
    ConfirmDirectPurchaseUseCase(authorized()).execute(
        proc_conn, actor_user_id="u1", direct_purchase_id=created.entity_id,
        operation_id="dp-confirm", payment_source="PETTY_CASH")

    summary = dispatch_procurement_outbox(proc_conn, bus)
    assert summary["dispatched"] >= 1
    names = bus.names()
    drafted = next(payload for name, payload in bus.published
                   if name == "DIRECT_PURCHASE_DRAFTED")
    assert drafted["schema_version"] == 1
    assert drafted["correlation_id"] == drafted["operation_id"]
    assert drafted["causation_id"] is None
    # received → inventory; immediate payment → treasury
    assert "PURCHASE_STOCK_ENTRY_REGISTERED" in names
    assert "SUPPLIER_PAYMENT_SCHEDULED" in names
    # outbox rows are now marked dispatched (no re-publish on a second pass)
    again = dispatch_procurement_outbox(proc_conn, bus)
    assert again["dispatched"] == 0


def test_outbox_failure_is_durable_and_dead_letters(proc_conn):
    payload = json.dumps({
        "event_id": "event-1", "event_name": "BROKEN", "operation_id": "op-1",
        "schema_version": 1, "correlation_id": "op-1",
    })
    proc_conn.execute(
        "INSERT INTO procurement_outbox"
        " (id,event_id,event_name,payload_json,operation_id,status,created_at)"
        " VALUES (?,?,?,?,?,'PENDING',?)",
        ("out-1", "event-1", "BROKEN", payload, "op-1", "2026-01-01T00:00:00+00:00"),
    )
    proc_conn.commit()

    class BrokenBus:
        def publish(self, *args, **kwargs):
            raise RuntimeError("downstream unavailable")

    result = dispatch_procurement_outbox(proc_conn, BrokenBus(), max_attempts=1)
    row = proc_conn.execute(
        "SELECT status,attempt_count,last_error FROM procurement_outbox WHERE id='out-1'"
    ).fetchone()
    assert result["failed"] == 1
    assert row[0] == "DEAD_LETTER" and row[1] == 1
    assert "downstream unavailable" in row[2]


def test_outbox_dead_letters_malformed_payload_without_publishing(proc_conn):
    proc_conn.execute(
        "INSERT INTO procurement_outbox"
        " (id,event_id,event_name,payload_json,operation_id,status,created_at)"
        " VALUES (?,?,?,?,?,'PENDING',?)",
        ("out-malformed", "event-x", "BROKEN", "{}", "op-x",
         "2026-01-01T00:00:00+00:00"),
    )
    proc_conn.commit()
    bus = FakeBus()

    result = dispatch_procurement_outbox(proc_conn, bus, max_attempts=1)
    row = proc_conn.execute(
        "SELECT status,last_error FROM procurement_outbox WHERE id='out-malformed'"
    ).fetchone()

    assert result["failed"] == 1
    assert bus.published == []
    assert row[0] == "DEAD_LETTER"
    assert "missing required fields" in row[1]


def test_wiring_reports_subscriptions(proc_conn):
    bus = FakeBus()
    summary = wire_procurement(bus, proc_conn)
    assert summary["count"] >= 7
