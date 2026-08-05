"""PUR-11 — procurement integrations: inbound needs → requisitions, outbound
receipts → inventory, payables → CxP, immediate payment → treasury (never POS
cash), receipts → supplier performance, and the outbox → bus dispatch."""

import json
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
<<<<<<< HEAD
    payload = json.dumps({
        "event_id": "event-1", "event_name": "BROKEN", "operation_id": "op-1",
        "schema_version": 1, "correlation_id": "op-1",
    })
=======
>>>>>>> f877b14564fe37c44b2caeab736af2048b371ae2
    proc_conn.execute(
        "INSERT INTO procurement_outbox"
        " (id,event_id,event_name,payload_json,operation_id,status,created_at)"
        " VALUES (?,?,?,?,?,'PENDING',?)",
<<<<<<< HEAD
        ("out-1", "event-1", "BROKEN", payload, "op-1", "2026-01-01T00:00:00+00:00"),
=======
        ("out-1", "event-1", "BROKEN", "{}", "op-1", "2026-01-01T00:00:00+00:00"),
>>>>>>> f877b14564fe37c44b2caeab736af2048b371ae2
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


<<<<<<< HEAD
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


=======
>>>>>>> f877b14564fe37c44b2caeab736af2048b371ae2
def test_wiring_reports_subscriptions(proc_conn):
    bus = FakeBus()
    summary = wire_procurement(bus, proc_conn)
    assert summary["count"] >= 7
