"""OrdersDeliveryInternalNotifier — the "Internal" half of ORD-26's
notification scope. Writes to the REAL, already-canonical `notification_inbox`
table (`migrations/m000_base_schema.py`) — the same one the desktop ERP's own
bell/inbox already reads — rather than inventing a parallel table. Reuses
the RBAC tables (`usuarios`/`usuarios_roles`/`roles`) directly, same
role-resolution idea `whatsapp_service/erp/pos_notifier.py` already applies
for its own (WA-microservice-side, legacy-integer-id) staff alerts, adapted
here to this backend's own UUIDv7 connection.

Deliberately does NOT reuse `pos_notifier.py`'s own `_ensure_notification_
inbox()` — that helper's `CREATE TABLE IF NOT EXISTS` defines EXTRA columns
(`dedupe_key`, `severity`) the canonical `m000_base_schema.py` table does
NOT have; since the table already exists by the time either runs, that
`CREATE TABLE IF NOT EXISTS` is a silent no-op and those columns never
actually appear — a real latent bug in that (separate, WhatsApp-microservice-
side) module, out of scope to fix here. This notifier only ever writes the
columns the canonical schema actually defines.

Never raises: like `OrdersDeliveryWhatsAppClient`, a failure to write an
internal alert must never fail the delivery operation that triggered it.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone

from backend.shared.ids import new_uuid


class OrdersDeliveryInternalNotifier:
    def __init__(self, connection) -> None:
        self._conn = connection

    def notify_roles(
        self, *, roles: tuple[str, ...], branch_id: str, tipo: str, titulo: str,
        cuerpo: str, datos: dict | None = None,
    ) -> int:
        """Writes one `notification_inbox` row per active staff member
        holding any of `roles`, scoped to `branch_id` (or any role grant
        with `sucursal_id` NULL/0, meaning "all branches" — same convention
        `usuarios_roles` already uses elsewhere). Returns how many rows were
        written; never raises."""
        try:
            employee_ids = self._resolve_employee_ids(roles=roles, branch_id=branch_id)
            if not employee_ids:
                return 0
            payload = json.dumps(datos or {}, ensure_ascii=False, default=str)
            now = datetime.now(timezone.utc).isoformat(timespec="seconds")
            written = 0
            for employee_id in employee_ids:
                self._conn.execute(
                    "INSERT INTO notification_inbox"
                    " (id, empleado_id, tipo, titulo, cuerpo, datos, sucursal_id, created_at)"
                    " VALUES (?,?,?,?,?,?,?,?)",
                    (new_uuid(), employee_id, tipo, titulo, cuerpo, payload, branch_id, now))
                written += 1
            return written
        except Exception:  # noqa: BLE001 - an alert failure must never fail the operation
            return 0

    def _resolve_employee_ids(self, *, roles: tuple[str, ...], branch_id: str) -> list[str]:
        if not roles:
            return []
        placeholders = ",".join("?" * len(roles))
        rows = self._conn.execute(
            f"""
            SELECT DISTINCT u.id
            FROM usuarios u
            JOIN usuarios_roles ur ON ur.usuario_id = u.id
            JOIN roles r ON r.id = ur.rol_id
            WHERE LOWER(r.nombre) IN ({placeholders})
              AND (ur.sucursal_id = ? OR ur.sucursal_id IS NULL OR ur.sucursal_id = '0')
              AND COALESCE(u.activo, 1) = 1
            """,
            (*[role.lower() for role in roles], branch_id),
        ).fetchall()
        return [row[0] for row in rows]
