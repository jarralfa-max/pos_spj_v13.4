"""Cross-bounded-context EventBus wiring — the composition root's event step.

`CompositionRoot`/`ServiceRegistry` (see `composition_root.py`) resolve lazy,
typed services; they do not subscribe anything onto the EventBus. Each
bounded context owns its own `wire_<context>()` function (e.g.
`backend/application/procurement/integrations/wiring.py::wire_procurement`),
but until something calls it against the LIVE bus, that context's events
publish into a void — publishers and handlers both exist, both pass their own
tests, and nothing connects them. `tests/architecture/
test_erp_chain_wiring_ratchet.py` measures exactly this gap.

This module is the single place that calls every context's wiring function
against `get_bus()` and the live connection, so "is X actually wired in
production" has one file to check instead of grepping call sites. Called
once from `frontend/desktop/app.py::main()`, after the database connection is
ready and before any use case can publish a cross-context event.
"""
from __future__ import annotations

import logging

from backend.shared.events.application_bus import get_bus

logger = logging.getLogger("spj.bootstrap.event_wiring")


def wire_cross_context_events(connection) -> dict:
    """Wire every bounded context's cross-context EventBus subscriptions.

    Returns a summary dict keyed by context name, useful for a startup
    diagnostic. Contexts whose wiring still needs an unresolved dependency
    (e.g. logistics needs a provisioned QR-signing secret) are deliberately
    left out here rather than wired with a fabricated one — see
    `backend/application/logistics/wiring.py::wire_logistics`.
    """
    from backend.application.pricing.integrations.wiring import wire_pricing
    from backend.application.procurement.integrations.wiring import wire_procurement

    bus = get_bus()
    summary = {
        "procurement": wire_procurement(bus, connection),
        "pricing": wire_pricing(bus, connection),
        "procurement_downstream_bridges": wire_procurement_downstream_bridges(bus, connection),
    }
    for context, result in summary.items():
        logger.info("cross-context wiring: %s -> %d subscriptions", context, result["count"])
    return summary


def wire_procurement_downstream_bridges(bus, connection) -> dict:
    """The four downstream consumers of procurement's own derived events
    (`PAYABLE_CREATED`, `SUPPLIER_PAYMENT_SCHEDULED`,
    `PURCHASE_STOCK_ENTRY_REGISTERED` — published by `wire_procurement`'s
    translators, see `downstream_translators.py`), all confirmed to have no
    live subscriber before this and no collision with each other.

    `CanonicalPurchaseStockEntryHandler` (inventory) is explicitly documented
    and tested (`tests/integration/procurement/test_pipeline_end_to_end.py`,
    docstring: "the CANONICAL stock handler") as procurement's real canonical
    stock-entry path — it posts a `PURCHASE_RECEIPT` movement + creates
    traceability lots. `CanonicalPurchaseRecipeExplosionHandler` is
    independent, additional behaviour on the SAME event (transformación-en-
    compra: buying a formulated product like marinated chicken also consumes
    its raw-material components as a separate `ADJUSTMENT_OUT`) — different
    products, different movement type, no overlap with the stock-entry
    handler. `ProcurementPayableBridgeHandler` (finance) creates the CxP for
    a CREDIT purchase AND its balanced recognition journal entry (CLAUDE.md
    §11) — its own docstring: "nothing subscribed it to this event. A
    matched supplier invoice therefore created no Payable... at all in
    production." `ProcurementImmediatePaymentBridgeHandler` (finance) is the
    CONTADO counterpart — a direct purchase confirmed with immediate payment
    never books a CxP at all (by design, see `ConfirmDirectPurchaseUseCase`'s
    own comment), so this posts the purchase recognition + settlement as one
    balanced entry straight to the resolved treasury account instead. See
    that handler's own module docstring for the (deliberately conservative,
    fail-closed) `payment_source` → `TreasuryAccountType` resolution.

    ⚠️ COLLISION WARNING for whoever eventually wires the separate,
    flag-gated INV-27 cutover (`backend/application/inventory/cutover/
    canonical_cutover.py::CanonicalInventoryCutover`, which subscribes
    `PurchaseReceiptHandler`/`DirectPurchaseReceiptHandler` DIRECTLY onto
    procurement's RAW `GOODS_RECEIPT_COMPLETED`/`DIRECT_PURCHASE_RECEIVED` —
    one hop earlier than the translator-derived event this function's
    stock-entry handler consumes). Migration 134 already persists that
    cutover's flag as ON in every real database, but nothing calls
    `CanonicalInventoryCutover.wire()` against the live bus today, so this is
    not yet a live conflict. If a future session wires THAT, it must first
    either drop `PurchaseReceiptHandler`/`DirectPurchaseReceiptHandler` from
    its `CANONICAL_HANDLER_CLASSES` (procurement's receipt handling is
    already covered here) or the same receipt will post its `PURCHASE_RECEIPT`
    ledger movement TWICE. This function's own regression test
    (`test_purchase_stock_entry_registered_has_exactly_three_subscribers`)
    only guards against an UNEXPECTED subscriber appearing on the SAME
    event/bus — it cannot see a future `CanonicalInventoryCutover.wire()`
    call, so re-read this warning before adding one.
    """
    from backend.application.event_handlers.finance.procurement_immediate_payment_bridge import (
        ProcurementImmediatePaymentBridgeHandler,
    )
    from backend.application.event_handlers.finance.procurement_payable_bridge import (
        ProcurementPayableBridgeHandler,
    )
    from backend.application.event_handlers.inventory.purchase_recipe_explosion_bridge import (
        CanonicalPurchaseRecipeExplosionHandler,
    )
    from backend.application.event_handlers.inventory.purchase_stock_entry_bridge import (
        CanonicalPurchaseStockEntryHandler,
    )

    payable_bridge = ProcurementPayableBridgeHandler(connection)
    immediate_payment_bridge = ProcurementImmediatePaymentBridgeHandler(connection)
    stock_entry = CanonicalPurchaseStockEntryHandler(connection)
    recipe_explosion = CanonicalPurchaseRecipeExplosionHandler(connection)

    bus.subscribe(payable_bridge.event_name, payable_bridge.handle, priority=50,
                  label="procurement_payable_bridge")
    bus.subscribe(immediate_payment_bridge.event_name, immediate_payment_bridge.handle,
                  priority=50, label="procurement_immediate_payment_bridge")
    bus.subscribe(stock_entry.event_name, stock_entry.handle, priority=100,
                  label="procurement_purchase_stock_entry")
    bus.subscribe(recipe_explosion.event_name, recipe_explosion.handle, priority=100,
                  label="procurement_purchase_recipe_explosion")

    return {
        "subscribed": [
            f"{payable_bridge.event_name}->ProcurementPayableBridgeHandler",
            f"{immediate_payment_bridge.event_name}->ProcurementImmediatePaymentBridgeHandler",
            f"{stock_entry.event_name}->CanonicalPurchaseStockEntryHandler",
            f"{recipe_explosion.event_name}->CanonicalPurchaseRecipeExplosionHandler",
        ],
        "count": 4,
    }
