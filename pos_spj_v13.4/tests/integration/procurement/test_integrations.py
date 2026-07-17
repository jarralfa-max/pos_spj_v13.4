"""PUR-11 — procurement integrations: inbound needs → requisitions, outbound
receipts → inventory, payables → CxP, immediate payment → treasury (never POS
cash), receipts → supplier performance, and the outbox → bus dispatch."""

from decimal import Decimal

from backend.application.procurement.integrations.procurement_outbox_dispatcher import (
    dispatch_procurement_outbox,
)
from backend.application.procurement.integrations.replenishment_intake import (
    ReplenishmentIntakeHandler,
)
from backend.application.procurement.integrations.wiring import wire_procurement
from backend.application.procurement.use_cases.direct_purchase_use_cases import (
    ConfirmDirectPurchaseUseCase,
    CreateDirectPurchaseUseCase,
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


# ── inbound: needs → requisitions ────────────────────────────────────────────
def test_replenishment_need_creates_requisition(proc_conn):
    handler = ReplenishmentIntakeHandler(proc_conn)
    out = handler.handle({
        "event_id": "need-1", "event_name": ReplenishmentNeedEvents.STOCK_REPLENISHMENT_REQUIRED,
        "branch_id": "br-1", "product_id": "p1", "quantity": "12"})
    assert out["success"] and out["requisition_id"]
    rows = proc_conn.execute("SELECT COUNT(*) FROM purchase_requisitions").fetchone()[0]
    assert rows == 1


def test_replenishment_intake_is_idempotent(proc_conn):
    handler = ReplenishmentIntakeHandler(proc_conn)
    payload = {"event_id": "need-x", "branch_id": "br-1",
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
    assert "INVENTORY_ADJUSTMENT_REGISTERED" in names
    assert "SUPPLIER_PERFORMANCE_RECORDED" in names
    inv = next(p for n, p in bus.published if n == "INVENTORY_ADJUSTMENT_REGISTERED")
    assert inv["reason"] == "PURCHASE_RECEIPT"
    assert inv["lines"][0]["quantity"] == "8"


def test_payable_event_translates_to_cxp(proc_conn):
    bus = FakeBus()
    wire_procurement(bus, proc_conn)
    bus.publish("PURCHASE_PAYABLE_CREATED", {
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

    created = CreateDirectPurchaseUseCase().execute(
        proc_conn, actor_user_id="u1", operation_id="dp-op", supplier_id="s1",
        branch_id="br-1", warehouse_id="wh-1",
        lines=[{"product_id": "p1", "description": "Pollo", "quantity": "3",
                "unit_cost": "100", "tax": "48"}])
    ConfirmDirectPurchaseUseCase().execute(
        proc_conn, actor_user_id="u1", direct_purchase_id=created.entity_id,
        operation_id="dp-confirm", payment_source="PETTY_CASH")

    summary = dispatch_procurement_outbox(proc_conn, bus)
    assert summary["dispatched"] >= 1
    names = bus.names()
    # received → inventory; immediate payment → treasury
    assert "INVENTORY_ADJUSTMENT_REGISTERED" in names
    assert "SUPPLIER_PAYMENT_SCHEDULED" in names
    # outbox rows are now marked dispatched (no re-publish on a second pass)
    again = dispatch_procurement_outbox(proc_conn, bus)
    assert again["dispatched"] == 0


def test_wiring_reports_subscriptions(proc_conn):
    bus = FakeBus()
    summary = wire_procurement(bus, proc_conn)
    assert summary["count"] >= 7
