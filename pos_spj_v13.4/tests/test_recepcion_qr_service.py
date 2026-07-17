# tests/test_recepcion_qr_service.py
"""QR reception — regression net, rewritten against the CANONICAL contract (PUR-13).

The legacy `RecepcionQRService.procesar_recepcion` (direct inventory write) was
removed. The same characterization (weighted-average cost with prior stock, stock
sync, traceability, receipt) is now asserted through the canonical pipeline:
CompleteQrReceptionUseCase → procurement outbox → translator →
PurchaseStockEntryHandler. The service's read/traceability helpers keep coverage.

Note: this test builds a minimal WORKING inventory schema on purpose. The full
`engine.up` inventory trigger (trg_recalc_inventario_actual) has a pre-existing
bug — it inserts into inventario_actual without the NOT NULL `id`, so ANY movement
raises there; that is an inventory-engine issue outside PUR-13's scope.
"""
import json
import sqlite3

import pytest

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
    create_procurement_schema(conn)
    # traceability tables
    conn.execute("CREATE TABLE trazabilidad_qr (uuid_qr TEXT PRIMARY KEY, estado TEXT,"
                 " datos_extra TEXT, fecha_recepcion TEXT, recepcion_id TEXT)")
    conn.execute("CREATE TABLE contenedores_qr (uuid_qr TEXT PRIMARY KEY, estado TEXT,"
                 " sucursal_destino TEXT, viaje_actual INTEGER DEFAULT 0, updated_at TEXT)")
    # minimal WORKING inventory schema (id autoincrement + correct trigger)
    conn.execute("CREATE TABLE inventario_actual (id INTEGER PRIMARY KEY, producto_id TEXT,"
                 " sucursal_id TEXT, cantidad REAL DEFAULT 0, costo_promedio REAL DEFAULT 0,"
                 " ultima_actualizacion TEXT, UNIQUE(producto_id, sucursal_id))")
    conn.execute("CREATE TABLE movimientos_inventario (id TEXT PRIMARY KEY, producto_id TEXT,"
                 " tipo TEXT, tipo_movimiento TEXT, cantidad REAL, costo_unitario REAL,"
                 " descripcion TEXT, referencia TEXT, referencia_id TEXT, referencia_tipo TEXT,"
                 " proveedor_id TEXT, usuario TEXT, sucursal_id TEXT)")
    conn.execute("CREATE TABLE productos (id TEXT PRIMARY KEY, existencia REAL DEFAULT 0,"
                 " precio_compra REAL DEFAULT 0)")
    conn.execute("""
        CREATE TRIGGER trg_recalc_inventario_actual
        AFTER INSERT ON movimientos_inventario
        WHEN NEW.producto_id IS NOT NULL AND NEW.sucursal_id IS NOT NULL
        BEGIN
            INSERT INTO inventario_actual (producto_id, sucursal_id, cantidad, ultima_actualizacion)
            VALUES (NEW.producto_id, NEW.sucursal_id,
                CASE WHEN NEW.tipo IN ('entrada','COMPRA') THEN NEW.cantidad ELSE -NEW.cantidad END,
                datetime('now'))
            ON CONFLICT(producto_id, sucursal_id) DO UPDATE SET
                cantidad = inventario_actual.cantidad +
                    CASE WHEN NEW.tipo IN ('entrada','COMPRA') THEN NEW.cantidad ELSE -NEW.cantidad END;
        END""")
    return conn


def _seed(conn):
    pid = "p1"
    conn.execute("INSERT INTO productos (id, existencia, precio_compra) VALUES (?,?,?)",
                 (pid, 5.0, 40.0))
    conn.execute("INSERT INTO inventario_actual (producto_id, sucursal_id, cantidad,"
                 " costo_promedio) VALUES (?,?,?,?)", (pid, "1", 5.0, 40.0))
    datos = {"proveedor_id": "prov1", "condicion_pago": "liquidado",
             "metodo_pago": "efectivo", "monto_pagado": 500.0, "monto_total": 500.0}
    conn.execute("INSERT INTO trazabilidad_qr (uuid_qr, estado, datos_extra)"
                 " VALUES ('QR1','asignado',?)", (json.dumps(datos),))
    conn.execute("INSERT INTO contenedores_qr (uuid_qr, estado, viaje_actual)"
                 " VALUES ('QR1','en_transito',0)")
    conn.commit()
    return pid


def test_qr_reception_canonical_effects_match_legacy():
    from backend.application.event_handlers.inventory.purchase_stock_entry_handler import (
        PurchaseStockEntryHandler,
    )
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
    wire_procurement(bus, conn)  # DIRECT_PURCHASE_RECEIVED → PURCHASE_STOCK_ENTRY_REGISTERED
    bus.subscribe(PURCHASE_STOCK_ENTRY_REGISTERED, PurchaseStockEntryHandler(conn).handle)

    result = CompleteQrReceptionUseCase().execute(
        conn, actor_user_id="ana", operation_id=new_uuid(), uuid_qr="QR1",
        items=[{"product_id": pid, "quantity": "10", "unit_cost": "50"}],
        branch_id="1", warehouse_id="1")
    assert result.success
    dispatch_procurement_outbox(conn, bus)

    # 5@40 + 10@50 → 15 unidades, costo promedio ponderado 46.666…
    inv = conn.execute("SELECT cantidad, costo_promedio FROM inventario_actual"
                       " WHERE producto_id=? AND sucursal_id='1'", (pid,)).fetchone()
    assert inv[0] == 15.0 and round(inv[1], 2) == 46.67

    prod = conn.execute("SELECT existencia, precio_compra FROM productos WHERE id=?",
                        (pid,)).fetchone()
    assert prod[0] == 15.0 and prod[1] == 50.0

    mov = conn.execute("SELECT tipo, tipo_movimiento, cantidad FROM movimientos_inventario"
                       " WHERE producto_id=?", (pid,)).fetchone()
    assert mov[0] == "entrada" and mov[1] == "COMPRA" and mov[2] == 10.0

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
