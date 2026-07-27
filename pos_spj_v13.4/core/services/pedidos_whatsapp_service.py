# core/services/pedidos_whatsapp_service.py
"""
PedidosWhatsappService — operaciones de la cola de pedidos WhatsApp del POS.

Ruta canónica: UI (VentanaPedidos / diálogos) → PedidosWhatsappService → DB.
Los diálogos son captura-only: no ejecutan SQL ni commits (Remediación D).
"""
from __future__ import annotations

import logging

logger = logging.getLogger("spj.services.pedidos_wa")


class PedidosWhatsappService:
    def __init__(self, db):
        self.db = db

    # ── Lecturas ──────────────────────────────────────────────────────────────
    def listar_items(self, pedido_id) -> list:
        rows = self.db.execute(
            "SELECT * FROM pedidos_whatsapp_items WHERE pedido_id=?", (pedido_id,)
        ).fetchall()
        return [dict(r) for r in rows]

    def listar_repartidores(self) -> list:
        rows = self.db.execute(
            "SELECT id, nombre FROM drivers WHERE activo=1"
        ).fetchall()
        return [{"id": r[0], "nombre": r[1]} for r in rows]

    def get_detalle(self, pedido_id) -> dict:
        pedido = self.db.execute(
            "SELECT * FROM pedidos_whatsapp WHERE id=?", (pedido_id,)
        ).fetchone()
        if not pedido:
            return {}
        items = self.db.execute(
            "SELECT * FROM pedidos_whatsapp_items WHERE pedido_id=?", (pedido_id,)
        ).fetchall()
        return {"pedido": dict(pedido), "items": [dict(i) for i in items]}

    # ── Escrituras ────────────────────────────────────────────────────────────
    def ajustar_pesos(self, pedido_id, pesos: dict) -> float:
        """Aplica los pesos capturados ({item_id: peso}); recalcula subtotal con el
        precio unitario de cada ítem, actualiza el total del pedido y lo pasa a
        'pesando'. Devuelve el total nuevo."""
        total_nuevo = 0.0
        for item_id, peso in pesos.items():
            row = self.db.execute(
                "SELECT precio_unitario FROM pedidos_whatsapp_items WHERE id=?",
                (item_id,)
            ).fetchone()
            precio = float(row[0]) if row and row[0] is not None else 0.0
            subtotal = round(float(peso) * precio, 2)
            total_nuevo += subtotal
            self.db.execute(
                "UPDATE pedidos_whatsapp_items SET cantidad_pesada=?, subtotal=? WHERE id=?",
                (peso, subtotal, item_id)
            )
        total_nuevo = round(total_nuevo, 2)
        self.db.execute(
            "UPDATE pedidos_whatsapp SET total=?, estado='pesando' WHERE id=?",
            (total_nuevo, pedido_id)
        )
        try: self.db.commit()
        except Exception: pass
        return total_nuevo

    def asignar_repartidor(self, pedido_id, repartidor_id) -> None:
        self.db.execute(
            "UPDATE pedidos_whatsapp SET repartidor_id=?, estado='listo' WHERE id=?",
            (repartidor_id, pedido_id)
        )
        try: self.db.commit()
        except Exception: pass
