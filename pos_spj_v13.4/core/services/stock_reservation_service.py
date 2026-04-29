from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import List, Dict

from core.events.event_bus import get_bus, AJUSTE_INVENTARIO

logger = logging.getLogger("spj.stock_reserva")

# Reservas activas más antiguas que este umbral se consideran huérfanas
RESERVATION_TTL_MINUTES = 30


class StockReservationService:
    """Reserva/libera stock lógico para ventas suspendidas."""

    def __init__(self, db, branch_id: int = 1):
        self.db = db
        self.branch_id = branch_id
        self._ensure_table()

    def _ensure_table(self):
        # Usar execute() individual en lugar de executescript() para no emitir
        # un COMMIT implícito que rompería SAVEPOINTs activos del llamador.
        stmts = [
            """CREATE TABLE IF NOT EXISTS stock_reservas (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                folio       TEXT UNIQUE,
                branch_id   INTEGER NOT NULL,
                estado      TEXT NOT NULL DEFAULT 'activa',
                payload_json TEXT NOT NULL DEFAULT '[]',
                created_at  TEXT DEFAULT (datetime('now')),
                updated_at  TEXT DEFAULT (datetime('now')),
                expires_at  TEXT DEFAULT (datetime('now', '+30 minutes'))
            )""",
            """CREATE TABLE IF NOT EXISTS stock_reserva_detalles (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                reserva_id  INTEGER NOT NULL,
                producto_id INTEGER NOT NULL,
                cantidad    REAL NOT NULL,
                created_at  TEXT DEFAULT (datetime('now')),
                FOREIGN KEY (reserva_id) REFERENCES stock_reservas(id)
            )""",
            """CREATE INDEX IF NOT EXISTS idx_stock_reserva_detalles_lookup
                ON stock_reserva_detalles(producto_id, reserva_id)""",
            # Migración: agregar expires_at si la tabla ya existía sin ella
            """ALTER TABLE stock_reservas
               ADD COLUMN expires_at TEXT DEFAULT (datetime('now', '+30 minutes'))""",
        ]
        for stmt in stmts:
            try:
                self.db.execute(stmt)
            except Exception:
                pass  # columna ya existe, tabla ya existe — ignorar

    def expirar_huerfanas(self) -> int:
        """
        Libera automáticamente reservas activas cuyo expires_at ya pasó.
        Retorna la cantidad de reservas expiradas.
        """
        try:
            cur = self.db.execute("""
                UPDATE stock_reservas
                SET estado     = 'expirada',
                    updated_at = datetime('now')
                WHERE estado = 'activa'
                  AND expires_at IS NOT NULL
                  AND expires_at < datetime('now')
            """)
            count = cur.rowcount
            if count:
                logger.info("stock_reservas: %d reservas expiradas", count)
            return count
        except Exception as e:
            logger.debug("expirar_huerfanas: %s", e)
            return 0

    def stock_disponible(self, producto_id: int) -> float:
        self.expirar_huerfanas()
        row = self.db.execute(
            "SELECT COALESCE(quantity,0) FROM branch_inventory "
            "WHERE branch_id=? AND product_id=?",
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
        """
        Reserva stock para un folio de manera ATÓMICA dentro de un SAVEPOINT.
        Expira reservas huérfanas antes de validar disponibilidad.
        """
        import uuid as _uuid
        sp = f"sp_reserva_{_uuid.uuid4().hex[:8]}"

        self.expirar_huerfanas()

        self.db.execute(f"SAVEPOINT {sp}")
        try:
            # Validar disponibilidad DENTRO del SAVEPOINT — evita race conditions
            for item in items:
                pid = int(item["id"])
                cant = float(item["cantidad"])
                disp = self.stock_disponible(pid)
                if disp + 1e-6 < cant:
                    self.db.execute(f"ROLLBACK TO SAVEPOINT {sp}")
                    self.db.execute(f"RELEASE SAVEPOINT {sp}")
                    raise ValueError(
                        f"Stock insuficiente para reservar producto {pid}. "
                        f"Disponible={disp:.3f}, requerido={cant:.3f}"
                    )

            payload = [
                {"producto_id": int(i["id"]), "cantidad": float(i["cantidad"])}
                for i in items
            ]
            expires = f"datetime('now', '+{RESERVATION_TTL_MINUTES} minutes')"
            cur = self.db.execute(
                f"INSERT INTO stock_reservas(folio, branch_id, estado, payload_json, expires_at) "
                f"VALUES(?, ?, 'activa', ?, {expires})",
                (folio, self.branch_id, json.dumps(payload)),
            )
            reserva_id = int(cur.lastrowid)
            for p in payload:
                self.db.execute(
                    "INSERT INTO stock_reserva_detalles"
                    "(reserva_id, producto_id, cantidad) VALUES(?,?,?)",
                    (reserva_id, int(p["producto_id"]), float(p["cantidad"])),
                )

            self.db.execute(f"RELEASE SAVEPOINT {sp}")

        except ValueError:
            raise
        except Exception as exc:
            try:
                self.db.execute(f"ROLLBACK TO SAVEPOINT {sp}")
                self.db.execute(f"RELEASE SAVEPOINT {sp}")
            except Exception:
                pass
            raise RuntimeError(f"reservar() falló: {exc}") from exc

        get_bus().publish(AJUSTE_INVENTARIO, {
            "motivo": "stock_reservado", "folio": folio,
            "branch_id": self.branch_id,
        })
        return reserva_id

    def liberar(self, reserva_id: int, motivo: str = "cancelada") -> None:
        self.db.execute(
            "UPDATE stock_reservas SET estado=?, updated_at=datetime('now') "
            "WHERE id=? AND estado='activa'",
            (f"liberada:{motivo}", reserva_id),
        )
        get_bus().publish(AJUSTE_INVENTARIO, {
            "motivo": "stock_reserva_liberada",
            "reserva_id": reserva_id,
            "branch_id": self.branch_id,
        })
