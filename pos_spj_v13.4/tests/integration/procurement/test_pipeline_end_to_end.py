"""PUR-13 / INV-27 — end-to-end: a confirmed purchase updates PHYSICAL stock.

Proves the wired pipeline: direct-purchase confirm → procurement outbox →
dispatch → PURCHASE_STOCK_ENTRY_REGISTERED → the CANONICAL stock handler posts a
PURCHASE_RECEIPT to the inventory ledger. This is the guarantee that makes the QR
repoint non-regressing (canonical receipts move the real, POS-read projection).

Post-cutover contract: stock lands in ``inventory_balances`` and the traceability
lot (weight products) lands in the canonical ``inventory_lots`` — both via
``CanonicalPurchaseStockEntryHandler``. The legacy ``PurchaseStockEntryHandler``
and ``PurchaseLotEntryHandler`` (legacy ``inventario_actual`` / ``lotes`` writes)
are removed (P2).
"""

from decimal import Decimal

from backend.application.event_handlers.inventory.purchase_stock_entry_bridge import (
    CanonicalPurchaseStockEntryHandler,
)
from backend.application.inventory.queries import InventoryAvailabilityQueryService
from backend.application.procurement.integrations.downstream_events import (
    PURCHASE_STOCK_ENTRY_REGISTERED,
)
from backend.application.procurement.integrations.procurement_outbox_dispatcher import (
    dispatch_procurement_outbox,
)
from backend.application.procurement.integrations.wiring import wire_procurement
from backend.application.procurement.use_cases.direct_purchase_use_cases import (
    ConfirmDirectPurchaseUseCase,
    CreateDirectPurchaseUseCase,
)
from backend.infrastructure.db.schema.inventory_schema import create_inventory_schema


class Bus:
    def __init__(self):
        self._subs = {}

    def publish(self, name, payload, async_=False):
        for fn in self._subs.get(name, []):
            fn(payload)

    def subscribe(self, name, handler, priority=50, label=""):
        self._subs.setdefault(name, []).append(handler)


def _available(conn, product_id, branch_id="br-1"):
    return InventoryAvailabilityQueryService(conn).get_availability(
        product_id=product_id, branch_id=branch_id).available


def test_confirmed_purchase_updates_physical_stock(proc_conn):
    create_inventory_schema(proc_conn)
    proc_conn.commit()
    bus = Bus()
    wire_procurement(bus, proc_conn)
    bus.subscribe(PURCHASE_STOCK_ENTRY_REGISTERED,
                  CanonicalPurchaseStockEntryHandler(proc_conn).handle)

    created = CreateDirectPurchaseUseCase().execute(
        proc_conn, actor_user_id="u1", operation_id="e2e", supplier_id="s1",
        branch_id="br-1", warehouse_id="wh-1",
        lines=[{"product_id": "p1", "description": "Pollo", "quantity": "10",
                "unit_cost": "30"}])
    ConfirmDirectPurchaseUseCase().execute(
        proc_conn, actor_user_id="u1", direct_purchase_id=created.entity_id,
        operation_id="e2e-confirm", payment_source="PETTY_CASH")

    # nothing in the ledger until the outbox is dispatched
    assert proc_conn.execute("SELECT COUNT(*) FROM inventory_ledger").fetchone()[0] == 0

    dispatch_procurement_outbox(proc_conn, bus)

    # canonical projection now carries the receipt
    assert _available(proc_conn, "p1") == Decimal("10")
    mov = proc_conn.execute(
        "SELECT movement_type FROM inventory_ledger"
        " WHERE source_module='procurement'").fetchone()
    assert mov[0] == "PURCHASE_RECEIPT"


def test_confirmed_weight_purchase_creates_canonical_lot(proc_conn):
    create_inventory_schema(proc_conn)
    proc_conn.commit()
    bus = Bus()
    wire_procurement(bus, proc_conn)
    bus.subscribe(PURCHASE_STOCK_ENTRY_REGISTERED,
                  CanonicalPurchaseStockEntryHandler(proc_conn).handle)

    created = CreateDirectPurchaseUseCase().execute(
        proc_conn, actor_user_id="u1", operation_id="e2e-lot", supplier_id="prov1",
        branch_id="br-1", warehouse_id="wh-1",
        lines=[{"product_id": "pollo", "description": "Pollo", "quantity": "20",
                "unit_cost": "55", "inventory_unit": "KG"}])
    ConfirmDirectPurchaseUseCase().execute(
        proc_conn, actor_user_id="u1", direct_purchase_id=created.entity_id,
        operation_id="e2e-lot-c", payment_source="PETTY_CASH")
    dispatch_procurement_outbox(proc_conn, bus)

    # canonical stock AND a canonical traceability lot (FIFO by lot) for the weight
    # product — the whole pipeline creates the lot in inventory_lots (no legacy tables)
    assert _available(proc_conn, "pollo") == Decimal("20")
    lot = proc_conn.execute(
        "SELECT lot_code, origin_type FROM inventory_lots"
        " WHERE product_id='pollo'").fetchone()
    assert lot is not None and lot[0] and lot[1] == "PURCHASE"
