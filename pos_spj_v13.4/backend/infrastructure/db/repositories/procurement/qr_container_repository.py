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

    # ── writes (traceability only) ────────────────────────────────────────────
    def register_container(self, *, uuid_qr: str, internal_code: str | None,
                           description: str | None, origin_branch_id: str | None) -> None:
        """Register (or ignore if it exists) a freshly generated container."""
        self._execute(
            "INSERT OR IGNORE INTO contenedores_qr"
            " (uuid_qr, codigo_interno, descripcion, sucursal_origen)"
            " VALUES (?,?,?,?)", (uuid_qr, internal_code, description, origin_branch_id))

    def save_assignment(self, *, uuid_qr: str, supplier_id, origin_branch_id,
                        destination_branch_id, datos_extra: dict) -> None:
        """Assign a container to a supplier + products + payment terms. The
        reception later reads this datos_extra. Traceability only."""
        self._execute(
            "INSERT INTO trazabilidad_qr"
            " (uuid_qr, tipo, proveedor_id, sucursal_id, sucursal_destino, estado, datos_extra)"
            " VALUES (?,?,?,?,?,'asignado',?)"
            " ON CONFLICT(uuid_qr) DO UPDATE SET estado='asignado',"
            " proveedor_id=excluded.proveedor_id, sucursal_destino=excluded.sucursal_destino,"
            " datos_extra=excluded.datos_extra",
            (uuid_qr, "contenedor", supplier_id, origin_branch_id, destination_branch_id,
             json.dumps(datos_extra, ensure_ascii=False)))

    def mark_partial(self, uuid_qr: str) -> None:
        self._execute("UPDATE trazabilidad_qr SET estado='recepcion_parcial'"
                      " WHERE uuid_qr=?", (uuid_qr,))

    def mark_incident(self, uuid_qr: str, incident_json: str) -> None:
        self._execute(
            "UPDATE trazabilidad_qr SET estado='incidencia',"
            " datos_extra=json_patch(COALESCE(datos_extra,'{}'), ?) WHERE uuid_qr=?",
            (f'{{"incidencia":{incident_json}}}', uuid_qr))

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
