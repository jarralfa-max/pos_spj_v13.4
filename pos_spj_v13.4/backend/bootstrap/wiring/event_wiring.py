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
    from backend.application.cash_register.finance_wiring import wire_cash_register
    from backend.application.costing.wiring import wire_costing
    from backend.application.pricing.integrations.wiring import wire_pricing
    from backend.application.procurement.integrations.wiring import wire_procurement
    from backend.application.sales.integrations.wiring import wire_sales
    from backend.application.quality.wiring import wire_quality
    from backend.application.customers.integrations.sales_wiring import wire_customers_sales
    from backend.application.use_cases.hr.finance_wiring import (
        dispatch_hr_outbox,
        wire_hr_finance,
    )
    from backend.application.event_handlers.hr.cash_attendance_handlers import (
        wire_cash_attendance,
    )

    from backend.application.finance.wiring import wire_finance
    from backend.application.services.finance.finance_bootstrap import bootstrap_finance

    bus = get_bus()
    # FIN-ERP (2026-10-22): el catálogo financiero (perfiles contables) se siembra
    # ANTES de despachar lo pendiente de Caja, Compras o RR. HH. Nunca impide el
    # arranque: sin él, esos eventos quedan pendientes y visibles.
    try:
        bootstrap_finance(connection)
    except Exception:
        logger.exception("siembra inicial del catálogo financiero fallida")
    summary = {
        # La merma valuada llega al mayor (antes nadie la consumía).
        "finance": wire_finance(bus, connection),
        "procurement": wire_procurement(bus, connection),
        # Fase 6 (2026-09-18): la venta completada llega a contabilidad.
        "sales": wire_sales(bus, connection),
        # CRM-43 (2026-10-08): la compra llega al expediente del cliente (número de
        # compras, última compra, etapa). Se cableaba en core/events, ya borrado.
        "customers": wire_customers_sales(bus, connection),
        # CASH-26 (2026-10-07): el Corte Z y la custodia de Caja llegan a Finanzas.
        "cash_register": wire_cash_register(bus, connection),
        "pricing": wire_pricing(bus, connection),
        # Costos publica el costo real de lo producido (Precios ya lo escucha)
        # y el hecho contable de la producción, que aquí se entrega a Finanzas.
        "costing": wire_costing(bus, connection),
        # Calidad decide sobre lo producido; Procesamiento registra la decisión.
        "quality": wire_quality(bus, connection),
        "procurement_downstream_bridges": wire_procurement_downstream_bridges(bus, connection),
        # Auditoría Finanzas F21 (2026-10-10): la nómina pagada llega al mayor.
        "hr": wire_hr_finance(bus, connection),
        # Auditoría RRHH HR-03 (2026-10-14): apertura y cierre de caja registran
        # la asistencia del cajero (antes cero suscriptores).
        "hr_attendance": wire_cash_attendance(bus, connection),
        # Auditoría Fidelidad 968e0bc FID-04: lo vendido a crédito acumula al
        # cobrarse (antes nadie escuchaba COLLECTION_APPLIED).
        "loyalty": _wire_loyalty(bus, connection),
    }
    for context, result in summary.items():
        logger.info("cross-context wiring: %s -> %d subscriptions", context, result["count"])
    # Lo que RR. HH. dejó pendiente (p. ej. una nómina pagada con la app
    # cerrándose) se entrega al arrancar. Nunca impide el arranque.
    try:
        dispatch_hr_outbox(connection, bus)
    except Exception:
        logger.exception("despacho inicial de hr_outbox fallido")
    # Compras (2026-10-15): lo que quedó pendiente (p. ej. las CxP de compras a
    # crédito regularizadas por la migración 340, o un cierre a media
    # operación) se entrega al arrancar, no hasta la siguiente operación.
    try:
        from backend.application.procurement.integrations.procurement_outbox_dispatcher import (
            dispatch_procurement_outbox,
        )
        dispatch_procurement_outbox(connection, bus)
    except Exception:
        logger.exception("despacho inicial de procurement_outbox fallido")
    # Caja (auditoría CJA-04, 2026-10-16): un Corte Z o una entrega de valores
    # que quedó sin llegar a Finanzas (la app se cerró tras el commit) se entrega
    # al arrancar; antes esperaba a la siguiente operación de Caja, sin plazo.
    try:
        from backend.application.cash_register.finance_wiring import dispatch_cash_outbox
        dispatch_cash_outbox(connection, bus)
    except Exception:
        logger.exception("despacho inicial de cash_outbox fallido")
    # Fidelidad (auditoría 968e0bc FID-10): lo que una venta dejó pendiente
    # (puntos, canje, vales) se entregaba sólo en la siguiente operación del POS.
    try:
        loyalty_sales_tick(connection, bus)
    except Exception:
        logger.exception("despacho inicial de ventas a Fidelidad fallido")
    # Finanzas (FIN-ERP): merma valuada pendiente, vencimientos y finance_outbox.
    try:
        from backend.application.finance.wiring import finance_periodic_tick
        finance_periodic_tick(connection, bus)
    except Exception:
        logger.exception("ciclo inicial de Finanzas fallido")
    return summary


def _wire_loyalty(bus, connection) -> dict:
    from backend.application.loyalty.integrations.credit_collection import (
        wire_loyalty_finance,
    )
    return wire_loyalty_finance(bus, connection)


def loyalty_sales_tick(connection, bus) -> dict:
    """Entrega `sales_outbox` (Fidelidad acredita, retira o devuelve el canje;
    Finanzas asienta) y pasa el puente Fidelidad→Finanzas. Idempotente: los
    consumidores lo son por evento/documento. Lo usa el arranque y el ciclo
    periódico del shell."""
    from backend.application.loyalty.integrations.finance_posting import (
        post_loyalty_finance,
    )
    from backend.application.sales.integrations.wiring import dispatch_sales_outbox

    post_loyalty_finance(connection)
    ventas = dispatch_sales_outbox(connection, bus)
    post_loyalty_finance(connection)
    return {"sales_outbox": ventas}


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
    traceability lots. (Until 2026-10-16 a `CanonicalPurchaseRecipeExplosionHandler`
    also consumed the components of any purchased product with an active
    recipe — of ANY type, allowing negative stock. Removed by user decision,
    production audit 32cfbf: Compras records what was received; every
    transformation is recorded once, in Producción.) `ProcurementPayableBridgeHandler` (finance) creates the CxP for
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
    from backend.application.event_handlers.inventory.purchase_stock_entry_bridge import (
        CanonicalPurchaseStockEntryHandler,
    )

    from backend.application.event_handlers.finance.procurement_compensation_bridges import (
        ProcurementImmediatePaymentReversalHandler,
        ProcurementReturnCreditHandler,
    )
    from backend.application.event_handlers.inventory.goods_receipt_reversed_handler import (
        GoodsReceiptReversedHandler,
    )
    from backend.application.event_handlers.inventory.supplier_return_handler import (
        SupplierReturnHandler,
    )

    payable_bridge = ProcurementPayableBridgeHandler(connection)
    immediate_payment_bridge = ProcurementImmediatePaymentBridgeHandler(connection)
    stock_entry = CanonicalPurchaseStockEntryHandler(connection)

    bus.subscribe(payable_bridge.event_name, payable_bridge.handle, priority=50,
                  label="procurement_payable_bridge")
    bus.subscribe(immediate_payment_bridge.event_name, immediate_payment_bridge.handle,
                  priority=50, label="procurement_immediate_payment_bridge")
    bus.subscribe(stock_entry.event_name, stock_entry.handle, priority=100,
                  label="procurement_purchase_stock_entry")

    # Auditoría Compras d9f2bca C12: reversos y devoluciones COMPENSAN. Antes
    # estos cuatro eventos no tenían consumidor: cambiar el documento dejaba
    # existencias y dinero como si nada. La devolución mueve stock al
    # CONFIRMARSE (no en el borrador). Idempotentes por operation_id.
    receipt_reversal = GoodsReceiptReversedHandler(connection)
    supplier_return = SupplierReturnHandler(connection)
    payment_reversal = ProcurementImmediatePaymentReversalHandler(connection)
    return_credit = ProcurementReturnCreditHandler(connection)

    def _reverse_direct_purchase_receipts(payload: dict) -> None:
        for receipt_id in payload.get("goods_receipt_ids") or []:
            receipt_reversal.handle({**payload, "goods_receipt_id": receipt_id,
                                     "operation_id": f"{payload.get('operation_id')}:{receipt_id}"})

    bus.subscribe("GOODS_RECEIPT_REVERSED", receipt_reversal.handle, priority=100,
                  label="procurement_receipt_reversal_inventory")
    bus.subscribe("DIRECT_PURCHASE_REVERSED", _reverse_direct_purchase_receipts, priority=100,
                  label="procurement_direct_reversal_inventory")
    bus.subscribe("DIRECT_PURCHASE_REVERSED", payment_reversal.handle, priority=50,
                  label="procurement_direct_reversal_finance")
    bus.subscribe("PURCHASE_RETURN_CONFIRMED", supplier_return.handle, priority=100,
                  label="procurement_return_inventory")
    bus.subscribe("PURCHASE_RETURN_CONFIRMED", return_credit.handle, priority=50,
                  label="procurement_return_finance")
    bus.subscribe("PURCHASE_PAYABLE_CREDIT_REQUESTED", return_credit.handle, priority=50,
                  label="credit_procurement_return_finance")

    return {
        "subscribed": [
            f"{payable_bridge.event_name}->ProcurementPayableBridgeHandler",
            f"{immediate_payment_bridge.event_name}->ProcurementImmediatePaymentBridgeHandler",
            f"{stock_entry.event_name}->CanonicalPurchaseStockEntryHandler",
            "GOODS_RECEIPT_REVERSED->GoodsReceiptReversedHandler",
            "DIRECT_PURCHASE_REVERSED->GoodsReceiptReversedHandler",
            "DIRECT_PURCHASE_REVERSED->ProcurementImmediatePaymentReversalHandler",
            "PURCHASE_RETURN_CONFIRMED->SupplierReturnHandler",
            "PURCHASE_RETURN_CONFIRMED->ProcurementReturnCreditHandler",
            "PURCHASE_PAYABLE_CREDIT_REQUESTED->ProcurementReturnCreditHandler",
        ],
        "count": 9,
    }
