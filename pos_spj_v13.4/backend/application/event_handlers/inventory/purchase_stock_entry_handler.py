"""PurchaseStockEntryHandler (Inventory context).

Applies a procurement purchase receipt to physical stock, consuming the canonical
``PURCHASE_STOCK_ENTRY_REGISTERED`` event. This is where the legacy monolith's
in-line inventory mutation now lives — at its correct owner — so Compras never
writes inventory tables and the QR/direct/order receptions all flow through one
path.

Behavior replicated EXACTLY from the legacy ``RecepcionQRService.procesar_recepcion``:
- weighted-average cost computed BEFORE the movement (with the prior state);
- a ``movimientos_inventario`` row (tipo COMPRA) whose trigger updates
  ``inventario_actual.cantidad``; then ``costo_promedio`` is fixed;
- ``productos.existencia`` (sum across branches) + ``precio_compra`` synced.

Idempotent by ``event_id`` (a movement carrying that reference short-circuits a
replay). Atomic: all lines apply in one transaction or none do.
"""

from __future__ import annotations

import logging
from decimal import Decimal

from backend.shared.ids import new_uuid

logger = logging.getLogger("spj.inventory.purchase_stock_entry")

_ENTRY_TYPE = "COMPRA"


def _dec(value) -> Decimal:
    if value in (None, ""):
        return Decimal("0")
    return Decimal(str(value))


class PurchaseStockEntryHandler:
    event_name = "PURCHASE_STOCK_ENTRY_REGISTERED"

    def __init__(self, connection) -> None:
        self._conn = connection

    def handle(self, payload: dict) -> None:
        event_id = str(payload.get("event_id") or "").strip()
        if not event_id:
            logger.warning("stock entry: evento sin event_id; se ignora")
            return
        sucursal_id = str(payload.get("warehouse_id") or payload.get("branch_id") or "").strip()
        lines = payload.get("lines") or []
        if not sucursal_id or not lines:
            return
        if self._already_applied(event_id):
            logger.info("stock entry: evento %s ya aplicado (idempotente)", event_id)
            return

        usuario = str(payload.get("user_id") or "system")
        proveedor_id = payload.get("supplier_id")
        reference = f"REC {payload.get('goods_receipt_id') or payload.get('document_id') or ''}"
        try:
            for line in lines:
                self._apply_line(line, sucursal_id=sucursal_id, event_id=event_id,
                                 usuario=usuario, proveedor_id=proveedor_id,
                                 reference=reference)
            self._conn.commit()
        except Exception:
            rollback = getattr(self._conn, "rollback", None)
            if rollback is not None:
                rollback()
            raise

    # ── internals ────────────────────────────────────────────────────────────
    def _already_applied(self, event_id: str) -> bool:
        row = self._conn.execute(
            "SELECT 1 FROM movimientos_inventario WHERE referencia_id=? LIMIT 1",
            (event_id,)).fetchone()
        return row is not None

    def _apply_line(self, line: dict, *, sucursal_id: str, event_id: str, usuario: str,
                    proveedor_id, reference: str) -> None:
        product_id = str(line.get("product_id") or "")
        if not product_id:
            return
        qty = _dec(line.get("quantity"))
        cost = _dec(line.get("unit_cost"))
        if qty <= 0:
            return

        prev = self._conn.execute(
            "SELECT cantidad, costo_promedio FROM inventario_actual"
            " WHERE producto_id=? AND sucursal_id=?", (product_id, sucursal_id)).fetchone()
        cant_old = _dec(prev[0]) if prev and prev[0] is not None else Decimal("0")
        costo_old = _dec(prev[1]) if prev and prev[1] is not None else Decimal("0")
        nueva_cant = cant_old + qty
        costo_prom = ((cant_old * costo_old + qty * cost) / nueva_cant
                      if nueva_cant > 0 else cost)

        # Movement — the trigger trg_recalc_inventario_actual adds qty to
        # inventario_actual.cantidad. referencia_id carries event_id for idempotency.
        self._conn.execute(
            "INSERT INTO movimientos_inventario"
            " (id, producto_id, tipo, tipo_movimiento, cantidad, costo_unitario,"
            "  descripcion, referencia, referencia_id, referencia_tipo, proveedor_id,"
            "  usuario, sucursal_id)"
            " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (new_uuid(), product_id, "entrada", _ENTRY_TYPE, float(qty), float(cost),
             "Recepción de compra", reference, event_id, "PURCHASE_RECEIPT",
             proveedor_id, usuario, sucursal_id))

        # Fix the weighted-average cost (the trigger already set cantidad).
        self._conn.execute(
            "UPDATE inventario_actual SET costo_promedio=?,"
            " ultima_actualizacion=datetime('now')"
            " WHERE producto_id=? AND sucursal_id=?",
            (float(costo_prom), product_id, sucursal_id))

        # Sync productos.existencia (sum across branches) + last purchase cost.
        self._conn.execute(
            "UPDATE productos SET existencia="
            " (SELECT COALESCE(SUM(cantidad),0) FROM inventario_actual WHERE producto_id=?),"
            " precio_compra=? WHERE id=?",
            (product_id, float(cost), product_id))
