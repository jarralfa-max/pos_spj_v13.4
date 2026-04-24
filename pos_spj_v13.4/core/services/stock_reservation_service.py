from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import List, Dict

from core.events.event_bus import get_bus, AJUSTE_INVENTARIO

logger = logging.getLogger("spj.stock_reserva")


class StockReservationService:
    """Reserva/libera stock lógico para ventas suspendidas."""

    def __init__(self, db, branch_id: int = 1):
        self.db = db
        self.branch_id = branch_id
        self._ensure_table()

    def _ensure_table(self):
        self.db.executescript("""
            CREATE TABLE IF NOT EXISTS stock_reservas (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                folio TEXT UNIQUE,
                branch_id INTEGER NOT NULL,
                estado TEXT NOT NULL DEFAULT 'activa',
                payload_json TEXT NOT NULL DEFAULT '[]',
                created_at TEXT DEFAULT (datetime('now')),
                updated_at TEXT DEFAULT (datetime('now'))
            );
            CREATE TABLE IF NOT EXISTS stock_reserva_detalles (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                reserva_id INTEGER NOT NULL,
                producto_id INTEGER NOT NULL,
                cantidad REAL NOT NULL,
                created_at TEXT DEFAULT (datetime('now')),
                FOREIGN KEY (reserva_id) REFERENCES stock_reservas(id)
            );
            CREATE INDEX IF NOT EXISTS idx_stock_reserva_detalles_lookup
                ON stock_reserva_detalles(producto_id, reserva_id);
        """)
        try:
            self.db.commit()
        except Exception:
            pass

    def stock_disponible(self, producto_id: int) -> float:
        row = self.db.execute(
            "SELECT COALESCE(quantity,0) FROM branch_inventory WHERE branch_id=? AND product_id=?",
            (self.branch_id, producto_id),
        ).fetchone()
        fisico = float(row[0]) if row else 0.0
        row2 = self.db.execute(
            "SELECT COALESCE(SUM(d.cantidad),0) "
            "FROM stock_reserva_detalles d "
            "JOIN stock_reservas r ON r.id=d.reserva_id "
            "WHERE r.estado='activa' AND r.branch_id=? AND d.producto_id=?",
            (self.branch_id, producto_id),
        ).fetchone()
        reservado = float(row2[0]) if row2 and row2[0] is not None else 0.0
        return max(0.0, fisico - reservado)

    def reservar(self, folio: str, items: List[Dict]) -> int:
        # Validación previa
        for item in items:
            pid = int(item["id"])
            cant = float(item["cantidad"])
            disp = self.stock_disponible(pid)
            if disp + 1e-6 < cant:
                raise ValueError(f"Stock insuficiente para reservar producto {pid}. Disponible={disp:.3f}, requerido={cant:.3f}")

        payload = [
            {"producto_id": int(i["id"]), "cantidad": float(i["cantidad"])}
            for i in items
        ]
        cur = self.db.execute(
            "INSERT INTO stock_reservas(folio, branch_id, estado, payload_json) VALUES(?,?, 'activa', ?)",
            (folio, self.branch_id, json.dumps(payload)),
        )
        reserva_id = int(cur.lastrowid)
        for p in payload:
            self.db.execute(
                "INSERT INTO stock_reserva_detalles(reserva_id, producto_id, cantidad) VALUES(?,?,?)",
                (reserva_id, int(p["producto_id"]), float(p["cantidad"])),
            )
        try:
            self.db.commit()
        except Exception:
            pass
        get_bus().publish(AJUSTE_INVENTARIO, {"motivo": "stock_reservado", "folio": folio, "branch_id": self.branch_id})
        return reserva_id

    def liberar(self, reserva_id: int, motivo: str = "cancelada") -> None:
        self.db.execute(
            "UPDATE stock_reservas SET estado=?, updated_at=datetime('now') WHERE id=? AND estado='activa'",
            (f"liberada:{motivo}", reserva_id),
        )
        try:
            self.db.commit()
        except Exception:
            pass
        get_bus().publish(AJUSTE_INVENTARIO, {"motivo": "stock_reserva_liberada", "reserva_id": reserva_id, "branch_id": self.branch_id})
