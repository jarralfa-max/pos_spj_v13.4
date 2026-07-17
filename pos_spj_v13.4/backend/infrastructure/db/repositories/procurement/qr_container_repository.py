"""QrContainerRepository — QR-container traceability for procurement reception.

Reads the container assignment (supplier + payment terms carried on the QR) and
advances the container lifecycle (assigned → received / available). It touches
ONLY the traceability tables (trazabilidad_qr / contenedores_qr) — never
inventory, finance or cash tables. Repositories never commit; the UoW owns the
transaction. Tolerates missing tables on a fresh dev DB.
"""

from __future__ import annotations

import json
import sqlite3
from decimal import Decimal
from typing import Any


class QrContainerRepository:
    def __init__(self, connection: Any) -> None:
        self._conn = connection

    def _query_one(self, sql: str, params: tuple = ()) -> dict | None:
        try:
            cur = self._conn.execute(sql, params)
        except sqlite3.OperationalError:
            return None
        row = cur.fetchone()
        if row is None:
            return None
        cols = [c[0] for c in cur.description]
        return dict(zip(cols, row))

    def _execute(self, sql: str, params: tuple = ()) -> None:
        try:
            self._conn.execute(sql, params)
        except sqlite3.OperationalError:
            pass

    def read_assignment(self, uuid_qr: str) -> dict | None:
        """Return the QR assignment: supplier + payment terms + current state.

        Mirrors the legacy widget's read of ``trazabilidad_qr.datos_extra`` so the
        reception carries the same supplier/payment context. Money is Decimal.
        """
        row = self._query_one(
            "SELECT uuid_qr, estado, COALESCE(datos_extra,'{}') AS datos_extra"
            " FROM trazabilidad_qr WHERE uuid_qr=? LIMIT 1", (uuid_qr,))
        if row is None:
            return None
        try:
            extra = json.loads(row.get("datos_extra") or "{}")
        except (TypeError, ValueError):
            extra = {}
        return {
            "uuid_qr": row["uuid_qr"],
            "estado": row["estado"],
            "supplier_id": extra.get("proveedor_id"),
            "payment_condition": extra.get("condicion_pago", "liquidado"),
            "payment_method": extra.get("metodo_pago", "efectivo"),
            "amount_paid": Decimal(str(extra.get("monto_pagado", 0) or 0)),
            "amount_total": Decimal(str(extra.get("monto_total", 0) or 0)),
        }

    def is_received(self, uuid_qr: str) -> bool:
        row = self._query_one(
            "SELECT estado FROM trazabilidad_qr WHERE uuid_qr=? LIMIT 1", (uuid_qr,))
        return bool(row) and str(row.get("estado")) == "recibido"

    def mark_received(self, uuid_qr: str, *, receipt_id: str,
                      warehouse_id: str | None) -> None:
        """Advance the container to received/available. Traceability only."""
        self._execute(
            "UPDATE trazabilidad_qr SET estado='recibido',"
            " fecha_recepcion=datetime('now'), recepcion_id=? WHERE uuid_qr=?",
            (receipt_id, uuid_qr))
        self._execute(
            "UPDATE contenedores_qr SET estado='disponible', sucursal_destino=?,"
            " viaje_actual=COALESCE(viaje_actual,0)+1, updated_at=datetime('now')"
            " WHERE uuid_qr=?", (warehouse_id, uuid_qr))
