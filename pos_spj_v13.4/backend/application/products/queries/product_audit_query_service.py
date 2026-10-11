"""ProductAuditQueryService (PROD-22, §40) — bitácora del maestro de productos.

Desde la re-auditoría de agosto cada mutación de Productos escribe en
`product_audit_log` (quién, qué, antes/después, por qué, cuándo), pero no había
ninguna pantalla para consultarla: la auditoría existía sólo para quien abriera
la base. Read-only, parametrizado.
"""

from __future__ import annotations

import json


class ProductAuditQueryService:
    def __init__(self, connection) -> None:
        self._conn = connection

    def actions(self) -> list[str]:
        return [r[0] for r in self._conn.execute(
            "SELECT DISTINCT action FROM product_audit_log ORDER BY action").fetchall()]

    def list_entries(self, *, text: str | None = None, action: str | None = None,
                     limit: int = 500) -> list[dict]:
        """Más recientes primero. `text` busca en nombre/código del producto y
        en el usuario; `entity_id` puede no ser un producto (especie, unidad)."""
        sql = ("SELECT a.id, a.occurred_at, a.action, a.entity_id, a.user_id, "
               "a.authorized_by, a.reason, a.before, a.after, "
               "p.code AS product_code, p.name AS product_name, "
               "COALESCE(u.nombre, u.usuario, a.user_id) AS user_name "
               "FROM product_audit_log a "
               "LEFT JOIN products p ON p.id = a.entity_id "
               "LEFT JOIN usuarios u ON u.id = a.user_id WHERE 1=1")
        params: list = []
        if action:
            sql += " AND a.action = ?"
            params.append(action)
        if text and text.strip():
            like = f"%{text.strip()}%"
            sql += (" AND (p.name LIKE ? OR p.code LIKE ? OR u.nombre LIKE ? "
                    "OR u.usuario LIKE ?)")
            params.extend([like, like, like, like])
        sql += " ORDER BY a.occurred_at DESC, a.rowid DESC LIMIT ?"
        params.append(int(limit))
        rows = self._conn.execute(sql, params).fetchall()
        return [{
            "id": r[0], "occurred_at": r[1], "action": r[2], "entity_id": r[3],
            "user_id": r[4], "authorized_by": r[5], "reason": r[6],
            "before": _load(r[7]), "after": _load(r[8]),
            "product_code": r[9], "product_name": r[10], "user_name": r[11],
        } for r in rows]


def _load(raw):
    if not raw:
        return None
    try:
        return json.loads(raw)
    except (TypeError, ValueError):
        return raw
