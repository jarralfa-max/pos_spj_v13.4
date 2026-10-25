"""Cola de WhatsApp de Productos (PROD-22, §36) — drenado, consulta y reintento.

* `drain_product_whatsapp_outbox`: lo que corre el servicio de fondo de la app.
* `ProductWhatsAppOutboxQuery`: estado de la cola (teléfonos enmascarados).
* `RetryProductWhatsAppMessageUseCase`: devuelve a la cola un mensaje FAILED;
  exige `PRODUCTOS.whatsapp.gestionar`.
"""

from __future__ import annotations

from datetime import datetime, timezone

from backend.application.products.audit import record_product_audit_entry
from backend.application.products.authorization.policy import ProductsAuthorizationPolicy
from backend.application.products.permissions import ProductPermissions
from backend.application.security.unwired_policy import unwired


def drain_product_whatsapp_outbox(connection, *, client=None) -> dict:
    from backend.infrastructure.notifications.product_whatsapp_outbox_dispatcher import (
        ProductWhatsAppOutboxDispatcher,
    )
    return ProductWhatsAppOutboxDispatcher(connection, client=client).run_once()


def _mask(phone: str) -> str:
    digits = "".join(ch for ch in phone or "" if ch.isdigit())
    return f"•••• {digits[-4:]}" if len(digits) >= 4 else "••••"


class ProductWhatsAppOutboxQuery:
    def __init__(self, connection) -> None:
        self._conn = connection

    def recent(self, *, limit: int = 200) -> list[dict]:
        try:
            rows = self._conn.execute(
                "SELECT o.id, o.created_at, o.phone, o.message, o.status, o.attempts, "
                "o.last_error, o.next_attempt_at, o.sent_at, p.code, p.name "
                "FROM product_whatsapp_outbox o LEFT JOIN products p ON p.id = o.entity_id "
                "ORDER BY o.created_at DESC, o.rowid DESC LIMIT ?", (int(limit),)).fetchall()
        except Exception:  # cola aún no creada
            return []
        return [{"id": r[0], "created_at": r[1], "recipient": _mask(r[2]), "message": r[3],
                 "status": r[4], "attempts": int(r[5] or 0), "last_error": r[6] or "",
                 "next_attempt_at": r[7], "sent_at": r[8],
                 "product": f"{r[9]} · {r[10]}" if r[10] else ""} for r in rows]


class RetryProductWhatsAppMessageUseCase:
    def __init__(self, connection,
                 authorization: ProductsAuthorizationPolicy | None = None) -> None:
        self._conn = connection
        self._auth = authorization or unwired(ProductsAuthorizationPolicy)

    def execute(self, *, message_id: str, user_id: str | None,
                operation_id: str) -> tuple[bool, str]:
        self._auth.require(user_id or "", ProductPermissions.WHATSAPP_ALERTS_MANAGE)
        row = self._conn.execute(
            "SELECT status FROM product_whatsapp_outbox WHERE id=?", (message_id,)).fetchone()
        if row is None:
            return False, "El mensaje no existe"
        if row[0] != "FAILED":
            return False, "Sólo se reintentan los mensajes que fallaron"
        now = datetime.now(timezone.utc).isoformat(timespec="seconds")
        self._conn.execute(
            "UPDATE product_whatsapp_outbox SET status='PENDING', attempts=0, "
            "next_attempt_at=? WHERE id=?", (now, message_id))
        record_product_audit_entry(
            self._conn, action="PRODUCT_WHATSAPP_ALERT_RETRIED", entity_id=message_id,
            user_id=user_id or "", operation_id=operation_id)
        self._conn.commit()
        return True, "Mensaje devuelto a la cola; se enviará en el siguiente ciclo."
