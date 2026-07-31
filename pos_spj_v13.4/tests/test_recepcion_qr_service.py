# tests/test_recepcion_qr_service.py
"""QR reception — regression net, asserted against the CANONICAL contract.

The legacy `RecepcionQRService.procesar_recepcion` (direct inventory write) was
removed at PUR-13; the legacy `PurchaseStockEntryHandler` (which wrote
`inventario_actual` / `productos.existencia`) was removed at the Productos corte
(Fase C). QR reception now flows entirely canonically:
CompleteQrReceptionUseCase → procurement outbox → translator →
CanonicalPurchaseStockEntryHandler → PURCHASE_RECEIPT in the inventory ledger.
Stock is read from `inventory_balances` (the projection the POS reads); the
weighted-average cost is carried per ledger line, not as a running average in a
legacy cache. The service's read/traceability helpers keep coverage.
"""
import json
import sqlite3

from decimal import Decimal

from backend.shared.ids import new_uuid


class _Bus:
    def __init__(self):
        self._subs = {}

    def publish(self, name, payload, async_=False):
        for fn in self._subs.get(name, []):
            fn(payload)

    def subscribe(self, name, handler, priority=50, label=""):
        self._subs.setdefault(name, []).append(handler)


def _working_conn():
    conn = sqlite3.connect(":memory:")
    from backend.infrastructure.db.schema.procurement_schema import create_procurement_schema
    from backend.infrastructure.db.schema.inventory_schema import create_inventory_schema
    create_procurement_schema(conn)
    create_inventory_schema(conn)
    # traceability tables
    conn.execute("CREATE TABLE trazabilidad_qr (uuid_qr TEXT PRIMARY KEY, estado TEXT,"
                 " datos_extra TEXT, fecha_recepcion TEXT, recepcion_id TEXT)")
    conn.execute("CREATE TABLE contenedores_qr (uuid_qr TEXT PRIMARY KEY, estado TEXT,"
                 " sucursal_destino TEXT, viaje_actual INTEGER DEFAULT 0, updated_at TEXT)")
    conn.commit()
    return conn


def _seed(conn):
    datos = {"proveedor_id": "prov1", "condicion_pago": "liquidado",
             "metodo_pago": "efectivo", "monto_pagado": 500.0, "monto_total": 500.0}
    conn.execute("INSERT INTO trazabilidad_qr (uuid_qr, estado, datos_extra)"
                 " VALUES ('QR1','asignado',?)", (json.dumps(datos),))
    conn.execute("INSERT INTO contenedores_qr (uuid_qr, estado, viaje_actual)"
                 " VALUES ('QR1','en_transito',0)")
    conn.commit()
    return "p1"


def test_qr_reception_canonical_effects():
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
    from backend.application.procurement.use_cases.qr_reception_use_cases import (
        CompleteQrReceptionUseCase,
    )
    conn = _working_conn()
    pid = _seed(conn)
    bus = _Bus()
    stock_handler = CanonicalPurchaseStockEntryHandler(conn)
    # opening canonical stock: 5 units @ 40 at branch "1"
    stock_handler.handle({"event_id": "opening", "warehouse_id": "1", "branch_id": "1",
                          "goods_receipt_id": "OPEN-1",
                          "lines": [{"product_id": pid, "quantity": "5", "unit_cost": "40"}]})
    wire_procurement(bus, conn)  # DIRECT_PURCHASE_RECEIVED → PURCHASE_STOCK_ENTRY_REGISTERED
    bus.subscribe(PURCHASE_STOCK_ENTRY_REGISTERED, stock_handler.handle)

    result = CompleteQrReceptionUseCase().execute(
        conn, actor_user_id="ana", operation_id=new_uuid(), uuid_qr="QR1",
        items=[{"product_id": pid, "quantity": "10", "unit_cost": "50"}],
        branch_id="1", warehouse_id="1")
    assert result.success
    dispatch_procurement_outbox(conn, bus)

    # 5 (opening) + 10 (QR reception) → 15 units available in the canonical projection
    available = InventoryAvailabilityQueryService(conn).get_availability(
        product_id=pid, branch_id="1").available
    assert available == Decimal("15")

    # the QR receipt posted a canonical PURCHASE_RECEIPT carrying the line unit_cost
    line = conn.execute(
        "SELECT l.unit_cost FROM inventory_ledger_lines l"
        " JOIN inventory_ledger m ON m.id = l.movement_id"
        " WHERE l.product_id=? AND m.source_module='procurement'"
        " ORDER BY l.unit_cost DESC LIMIT 1", (pid,)).fetchone()
    assert Decimal(str(line[0])) == Decimal("50")

    tqr = conn.execute("SELECT estado, recepcion_id FROM trazabilidad_qr"
                       " WHERE uuid_qr='QR1'").fetchone()
    assert tqr[0] == "recibido" and tqr[1]
    conn.close()


def test_service_traceability_helpers_still_work():
    """The service keeps its read/traceability helpers (procesar_recepcion removed)."""
    from core.services.recepcion_qr_service import RecepcionQRService
    conn = _working_conn()
    _seed(conn)
    svc = RecepcionQRService(conn)
    assert not hasattr(svc, "procesar_recepcion")  # legacy direct write removed
    svc.marcar_recepcion_parcial("QR1")
    assert conn.execute("SELECT estado FROM trazabilidad_qr WHERE uuid_qr='QR1'"
                        ).fetchone()[0] == "recepcion_parcial"
    svc.marcar_incidencia("QR1", json.dumps({"tipo": "faltante"}))
    assert conn.execute("SELECT estado FROM trazabilidad_qr WHERE uuid_qr='QR1'"
                        ).fetchone()[0] == "incidencia"
    conn.close()
