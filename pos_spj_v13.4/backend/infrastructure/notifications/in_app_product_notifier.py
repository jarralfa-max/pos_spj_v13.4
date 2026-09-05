"""InAppProductNotifier (PROD-16, §36) — real in-app delivery for product alerts.

Before this existed, `ProductNotificationGateway`'s only implementation was
`InMemoryProductNotifier` (test/dev recorder) — no real channel existed for
either half of the "fan-out to in-app + WhatsApp" the module's own docstring
promised. Writes to the REAL, already-canonical `notification_inbox` table
(`migrations/m000_base_schema.py`) — the same one the desktop ERP's own
bell/inbox already reads — rather than inventing a parallel table. Mirrors
`backend/infrastructure/integrations/orders_delivery_internal_notifier.py`'s
established pattern for this exact table.

``recipient_ref`` is a user id (``usuarios.id``) — the same identity space
`ProductsAuthorizationPolicy`/every product use case already uses for
`user_id`, so callers of `ProductNotificationService.notify()` targeting this
channel pass user ids directly, no extra resolution step.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone

from backend.shared.ids import new_uuid


class InAppProductNotifier:
    """Implements `ProductNotificationGateway` for the IN_APP channel only —
    call `.send()` only when `channel == "IN_APP"` (the fan-out gateway
    enforces this)."""

    def __init__(self, connection) -> None:
        self._conn = connection

    def send(self, *, channel: str, recipient_ref: str, message: str,
             context: dict) -> None:
        payload = json.dumps(context or {}, ensure_ascii=False, default=str)
        now = datetime.now(timezone.utc).isoformat(timespec="seconds")
        branch_id = (context or {}).get("branch_id")
        self._conn.execute(
            "INSERT INTO notification_inbox "
            "(id, empleado_id, tipo, titulo, cuerpo, datos, sucursal_id, created_at) "
            "VALUES (?,?,?,?,?,?,?,?)",
            (new_uuid(), recipient_ref, "PRODUCTOS", "Alerta de producto",
             message, payload, branch_id, now))
