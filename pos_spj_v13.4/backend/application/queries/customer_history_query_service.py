# backend/application/queries/customer_history_query_service.py
"""
CustomerHistoryQueryService — lecturas de historial de cliente para UI.

Ruta canónica de lectura para el diálogo "Historial" de Clientes:
la UI PyQt no ejecuta SQL; consume este QueryService.

Reglas:
- `cliente_id` es UUID string (nunca int).
- Columnas canónicas: ventas.forma_pago (no metodo_pago),
  historico_puntos.cliente_id (no id_cliente).
- Si una tabla opcional no existe, devuelve lista vacía con warning
  controlado (no rompe la UI ni oculta el motivo en silencio).
"""
from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger("spj.queries.customer_history")


class CustomerHistoryQueryService:
    def __init__(self, db_conn: Any) -> None:
        self.db = db_conn

    # ── infra ────────────────────────────────────────────────────────────────
    def _table_exists(self, name: str) -> bool:
        row = self.db.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,)
        ).fetchone()
        return bool(row)

    # ── API pública ──────────────────────────────────────────────────────────
    def get_purchase_history(self, customer_id: str) -> list[dict]:
        """Ventas del cliente: fecha, total, forma_pago, puntos."""
        customer_id = str(customer_id or "").strip()
        if not customer_id or not self._table_exists("ventas"):
            return []
        rows = self.db.execute(
            """
            SELECT fecha, COALESCE(total, 0), COALESCE(forma_pago, ''),
                   COALESCE(loyalty_points, 0)
            FROM ventas
            WHERE cliente_id = ?
            ORDER BY fecha DESC
            """,
            (customer_id,),
        ).fetchall()
        return [
            {
                "fecha": r[0],
                "total": float(r[1] or 0),
                "forma_pago": str(r[2] or ""),
                "puntos_ganados": int(r[3] or 0),
            }
            for r in rows
        ]

    def get_points_history(self, customer_id: str) -> list[dict]:
        """Movimientos de puntos: fecha, tipo, puntos, saldo, descripción."""
        customer_id = str(customer_id or "").strip()
        if not customer_id or not self._table_exists("historico_puntos"):
            return []
        rows = self.db.execute(
            """
            SELECT fecha, COALESCE(tipo, ''), COALESCE(puntos, 0),
                   COALESCE(saldo_actual, 0), COALESCE(descripcion, '')
            FROM historico_puntos
            WHERE cliente_id = ?
            ORDER BY fecha DESC
            """,
            (customer_id,),
        ).fetchall()
        return [
            {
                "fecha": r[0],
                "tipo": str(r[1] or ""),
                "puntos": int(r[2] or 0),
                "saldo_actual": float(r[3] or 0),
                "descripcion": str(r[4] or ""),
            }
            for r in rows
        ]

    def get_credit_history(self, customer_id: str) -> list[dict]:
        """Movimientos de crédito (CxC). Tabla opcional → lista vacía."""
        customer_id = str(customer_id or "").strip()
        if not customer_id:
            return []
        if self._table_exists("movimientos_credito"):
            rows = self.db.execute(
                """
                SELECT fecha, COALESCE(tipo, ''), COALESCE(monto, 0),
                       COALESCE(descripcion, ''), COALESCE(usuario, '')
                FROM movimientos_credito
                WHERE cliente_id = ?
                ORDER BY fecha DESC
                """,
                (customer_id,),
            ).fetchall()
        elif self._table_exists("cuentas_por_cobrar"):
            # Fuente canónica de crédito cuando no hay tabla de movimientos
            rows = self.db.execute(
                """
                SELECT fecha, estado, COALESCE(monto_original, 0),
                       COALESCE('Folio ' || folio, ''), ''
                FROM cuentas_por_cobrar
                WHERE cliente_id = ?
                ORDER BY fecha DESC
                """,
                (customer_id,),
            ).fetchall()
        else:
            logger.warning(
                "get_credit_history: sin tablas de crédito (movimientos_credito/"
                "cuentas_por_cobrar) — devolviendo lista vacía"
            )
            return []
        return [
            {
                "fecha": r[0],
                "tipo": str(r[1] or ""),
                "monto": float(r[2] or 0),
                "descripcion": str(r[3] or ""),
                "usuario": str(r[4] or ""),
            }
            for r in rows
        ]
