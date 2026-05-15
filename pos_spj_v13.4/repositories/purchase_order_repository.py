"""
repositories/purchase_order_repository.py
──────────────────────────────────────────
Acceso a datos para Purchase Orders (PO).

Tabla: ordenes_compra + ordenes_compra_items (schema extendido por 077)
Sin lógica de negocio — solo CRUD + queries.
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime
from typing import Optional

logger = logging.getLogger("spj.repo.purchase_order")

# Estados válidos de PO
PO_STATES = ("ABIERTA", "PARCIAL", "RECIBIDA", "CERRADA", "CANCELADA",
             "borrador", "pendiente")  # legacy WA states preserved


class PurchaseOrderRepository:

    def __init__(self, conn):
        self.conn = conn

    # ── Creación desde PR ─────────────────────────────────────────────────────

    def create_from_pr(
        self,
        pr_id: int,
        pr_data: dict,
        usuario: str,
    ) -> tuple[int, str]:
        """
        Crea una PO derivada de una PR aprobada.
        Retorna (po_id, folio).
        NO afecta inventario, finanzas ni eventos.
        """
        folio = f"PO-{datetime.now().strftime('%Y%m%d%H%M%S')}-{uuid.uuid4().hex[:4].upper()}"
        cur = self.conn.execute(
            """INSERT INTO ordenes_compra
               (folio, proveedor_id, pr_id, sucursal_id, usuario,
                subtotal, iva_monto, total, metodo_pago,
                condicion_pago, plazo_dias, moneda, notas, doc_ref,
                estado, fecha_entrega_esperada)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (folio,
             pr_data.get("proveedor_id"),
             pr_id,
             pr_data.get("sucursal_id", 1),
             usuario,
             pr_data.get("subtotal", 0),
             pr_data.get("iva_monto", 0),
             pr_data.get("total", 0),
             pr_data.get("metodo_pago", "CONTADO"),
             pr_data.get("condicion_pago", "liquidado"),
             pr_data.get("plazo_dias", 0),
             pr_data.get("moneda", "MXN"),
             pr_data.get("notas", ""),
             pr_data.get("doc_ref", ""),
             "ABIERTA",
             None),
        )
        po_id = cur.lastrowid

        # Copiar items de la PR
        items = pr_data.get("items", [])
        self._save_items(po_id, items, source="pr_item")

        logger.info("PO creada: %s id=%d desde PR id=%d total=%.2f",
                    folio, po_id, pr_id, pr_data.get("total", 0))
        return po_id, folio

    def create_direct(
        self,
        proveedor_id: int,
        sucursal_id: int,
        usuario: str,
        items: list[dict],
        subtotal: float,
        iva_monto: float,
        total: float,
        metodo_pago: str = "CONTADO",
        condicion_pago: str = "liquidado",
        plazo_dias: int = 0,
        moneda: str = "MXN",
        notas: str = "",
        doc_ref: str = "",
    ) -> tuple[int, str]:
        """Crea una PO directa (sin PR previa). Para flujos de emergencia."""
        folio = f"PO-{datetime.now().strftime('%Y%m%d%H%M%S')}-{uuid.uuid4().hex[:4].upper()}"
        cur = self.conn.execute(
            """INSERT INTO ordenes_compra
               (folio, proveedor_id, sucursal_id, usuario,
                subtotal, iva_monto, total, metodo_pago,
                condicion_pago, plazo_dias, moneda, notas, doc_ref, estado)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (folio, proveedor_id, sucursal_id, usuario,
             subtotal, iva_monto, total, metodo_pago,
             condicion_pago, plazo_dias, moneda, notas, doc_ref, "ABIERTA"),
        )
        po_id = cur.lastrowid
        self._save_items(po_id, items)
        return po_id, folio

    def _save_items(self, po_id: int, items: list[dict],
                    source: str = "direct") -> None:
        for item in items:
            prod_id = item.get("product_id") or item.get("producto_id")
            qty     = item.get("qty") or item.get("cantidad", 0)
            cost    = item.get("unit_cost") or item.get("precio_unitario", 0)
            self.conn.execute(
                """INSERT INTO ordenes_compra_items
                   (orden_id, producto_id, nombre, cantidad, recibido,
                    precio_unitario, subtotal, unidad, lote, fecha_caducidad, notas)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
                (po_id, prod_id,
                 item.get("nombre", ""),
                 qty, 0,
                 cost,
                 round(qty * cost, 4),
                 item.get("unidad", "kg"),
                 item.get("lote", ""),
                 item.get("fecha_caducidad"),
                 item.get("notas", "")),
            )

    # ── Lectura ───────────────────────────────────────────────────────────────

    def get_by_id(self, po_id: int) -> Optional[dict]:
        row = self.conn.execute(
            "SELECT * FROM ordenes_compra WHERE id=?", (po_id,)
        ).fetchone()
        if not row:
            return None
        result = dict(row)
        result["items"] = self._get_items(po_id)
        return result

    def get_by_folio(self, folio: str) -> Optional[dict]:
        row = self.conn.execute(
            "SELECT * FROM ordenes_compra WHERE folio=?", (folio,)
        ).fetchone()
        if not row:
            return None
        result = dict(row)
        result["items"] = self._get_items(result["id"])
        return result

    def _get_items(self, po_id: int) -> list[dict]:
        rows = self.conn.execute(
            "SELECT * FROM ordenes_compra_items WHERE orden_id=? ORDER BY id",
            (po_id,),
        ).fetchall()
        return [dict(r) for r in rows]

    def list_open(self, sucursal_id: Optional[int] = None,
                  limit: int = 100) -> list[dict]:
        q = "SELECT * FROM ordenes_compra WHERE estado IN ('ABIERTA','PARCIAL')"
        params: list = []
        if sucursal_id:
            q += " AND sucursal_id=?"
            params.append(sucursal_id)
        q += " ORDER BY fecha_creacion DESC LIMIT ?"
        params.append(limit)
        return [dict(r) for r in self.conn.execute(q, params).fetchall()]

    # ── Transiciones de estado ────────────────────────────────────────────────

    def update_estado(self, po_id: int, nuevo_estado: str) -> bool:
        now = datetime.now().isoformat()
        fecha_rec = now if nuevo_estado in ("RECIBIDA", "PARCIAL") else None
        self.conn.execute(
            """UPDATE ordenes_compra
               SET estado=?, fecha_actualizacion=?,
                   fecha_recepcion=COALESCE(fecha_recepcion, ?)
               WHERE id=?""",
            (nuevo_estado, now, fecha_rec, po_id),
        )
        return self.conn.execute("SELECT changes()").fetchone()[0] > 0

    def update_item_received(self, po_id: int, producto_id: int,
                             qty_received: float) -> None:
        self.conn.execute(
            """UPDATE ordenes_compra_items
               SET recibido = recibido + ?
               WHERE orden_id=? AND producto_id=?""",
            (qty_received, po_id, producto_id),
        )

    def compute_po_completion(self, po_id: int) -> float:
        """Retorna fracción recibida (0.0–1.0). 1.0 = completamente recibida."""
        row = self.conn.execute(
            """SELECT
                 COALESCE(SUM(cantidad), 0) AS total_qty,
                 COALESCE(SUM(recibido), 0) AS total_rec
               FROM ordenes_compra_items WHERE orden_id=?""",
            (po_id,),
        ).fetchone()
        if not row or row["total_qty"] == 0:
            return 0.0
        return min(row["total_rec"] / row["total_qty"], 1.0)
