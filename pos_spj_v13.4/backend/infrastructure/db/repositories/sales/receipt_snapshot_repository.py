"""Foto del ticket de cada venta (comparativa de tickets main ↔ ERP, 2026-10-16).

Al imprimir por primera vez se guarda el documento COMPLETO que salió: diseño de
la versión de plantilla usada, encabezado y logo, renglones, puntos y mensajes
de ese momento. La reimpresión lo usa tal cual (decisión del usuario: «el
original, marcado»): una promoción nueva nunca aparece en un ticket viejo.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone

from backend.shared.ids import new_uuid


class SaleReceiptSnapshotRepository:
    def __init__(self, connection) -> None:
        self._conn = connection

    def get(self, sale_id: str) -> dict | None:
        try:
            row = self._conn.execute(
                "SELECT document_type, template_version_id, layout_json, header_json,"
                " payload_json, logo_path, created_at FROM sale_receipt_snapshots"
                " WHERE sale_id=?", (sale_id,)).fetchone()
        except sqlite3.OperationalError:
            return None
        if row is None:
            return None
        return {"document_type": row[0], "template_version_id": row[1], "layout_json": row[2],
                "header": json.loads(row[3] or "{}"), "payload": json.loads(row[4] or "{}"),
                "logo_path": row[5], "captured_at": row[6]}

    def save_if_absent(self, sale_id: str, document: dict) -> bool:
        """True si guardó; la primera foto manda y nunca se reescribe."""
        try:
            cur = self._conn.execute(
                "INSERT OR IGNORE INTO sale_receipt_snapshots (id, sale_id, document_type,"
                " template_version_id, layout_json, header_json, payload_json, logo_path,"
                " created_at) VALUES (?,?,?,?,?,?,?,?,?)",
                (new_uuid(), sale_id, document.get("document_type") or "SALE_TICKET",
                 document.get("template_version_id"), document["layout_json"],
                 json.dumps(document.get("header") or {}, ensure_ascii=False),
                 json.dumps(document.get("payload") or {}, ensure_ascii=False, default=str),
                 document.get("logo_path"),
                 datetime.now(timezone.utc).isoformat(timespec="seconds")))
        except sqlite3.OperationalError:
            return False
        return bool(cur.rowcount)
