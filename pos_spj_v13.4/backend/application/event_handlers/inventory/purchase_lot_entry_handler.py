"""PurchaseLotEntryHandler (Inventory context).

Creates a traceability lot per weight-tracked / perishable purchase-receipt line,
consuming ``PURCHASE_STOCK_ENTRY_REGISTERED``. This is the meat/poultry lot
behavior migrated out of the monolith (PurchaseService._crear_lotes_compra /
LoteService.registrar_lote) to its correct owner — enabling FIFO by lot, per-lot
costing, expiry alerts and full traceability.

A lot is created for lines that are weight-tracked (inventory_unit KG) or carry an
expiration/lot marker. numero_lote = ``{document_number}-P{product_id}`` and the
insert is idempotent (INSERT OR IGNORE), so a replayed event never duplicates a
lot. The physical stock itself is applied by PurchaseStockEntryHandler; this
handler only writes the ``lotes`` / ``movimientos_lote`` traceability tables.
"""

from __future__ import annotations

import logging
from decimal import Decimal

from backend.shared.ids import new_uuid

logger = logging.getLogger("spj.inventory.purchase_lot_entry")

_WEIGHT_UNITS = {"KG", "KILO", "KILOS", "KG."}


def _dec(value) -> Decimal:
    if value in (None, ""):
        return Decimal("0")
    return Decimal(str(value))


def _is_lot_tracked(line: dict) -> bool:
    unit = str(line.get("inventory_unit") or "").strip().upper()
    if unit in _WEIGHT_UNITS:
        return True
    return bool(line.get("expiration") or line.get("lot"))


class PurchaseLotEntryHandler:
    event_name = "PURCHASE_STOCK_ENTRY_REGISTERED"

    def __init__(self, connection) -> None:
        self._conn = connection

    def handle(self, payload: dict) -> None:
        event_id = str(payload.get("event_id") or "").strip()
        if not event_id:
            return
        lines = payload.get("lines") or []
        document = str(payload.get("document_number")
                       or payload.get("goods_receipt_id")
                       or payload.get("document_id") or event_id[:8])
        sucursal_id = str(payload.get("warehouse_id") or payload.get("branch_id") or "")
        proveedor_id = payload.get("supplier_id")
        usuario = str(payload.get("user_id") or "system")
        tracked = [ln for ln in lines if _is_lot_tracked(ln)]
        if not tracked:
            return
        try:
            for line in tracked:
                self._create_lot(line, document=document, sucursal_id=sucursal_id,
                                 proveedor_id=proveedor_id, usuario=usuario)
            self._conn.commit()
        except Exception:
            rollback = getattr(self._conn, "rollback", None)
            if rollback is not None:
                rollback()
            raise

    def _create_lot(self, line: dict, *, document: str, sucursal_id: str,
                    proveedor_id, usuario: str) -> None:
        product_id = str(line.get("product_id") or "")
        qty = _dec(line.get("quantity"))
        cost = _dec(line.get("unit_cost"))
        if not product_id or qty <= 0:
            return
        numero_lote = f"{document}-P{product_id}"
        # idempotent: a replayed event / duplicate line does not duplicate the lot.
        self._conn.execute(
            "INSERT OR IGNORE INTO lotes"
            " (id, producto_id, numero_lote, proveedor_id, peso_inicial_kg,"
            "  peso_actual_kg, costo_kg, fecha_caducidad, sucursal_id, observaciones,"
            "  estado, tipo_origen)"
            " VALUES (?,?,?,?,?,?,?,?,?,?,'activo','compra')",
            (new_uuid(), product_id, numero_lote, proveedor_id, float(qty), float(qty),
             float(cost), line.get("expiration"), sucursal_id,
             f"Compra {document}"))
        row = self._conn.execute(
            "SELECT id FROM lotes WHERE numero_lote=? AND producto_id=?",
            (numero_lote, product_id)).fetchone()
        if row:
            # movement is idempotent by (lote_id, referencia, tipo)
            exists = self._conn.execute(
                "SELECT 1 FROM movimientos_lote WHERE lote_id=? AND referencia=?"
                " AND tipo='recepcion' LIMIT 1", (row[0], document)).fetchone()
            if not exists:
                self._conn.execute(
                    "INSERT INTO movimientos_lote"
                    " (id, lote_id, tipo, cantidad_kg, referencia, usuario)"
                    " VALUES (?,?,'recepcion',?,?,?)",
                    (new_uuid(), row[0], float(qty), document, usuario))
