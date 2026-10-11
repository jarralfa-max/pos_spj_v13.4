"""ProductWhatsAppOutboxDispatcher (PROD-22, §36) — entrega la cola de WhatsApp.

Toma los mensajes PENDING cuyo turno llegó, los envía al microservicio y:
* si el microservicio confirma → SENT;
* si no (sin conexión, sin clave configurada, error) → reintenta más tarde con
  espera creciente; tras `MAX_ATTEMPTS` → FAILED, con el último error visible
  en Productos → Notificaciones (donde se puede reintentar a mano).

Corre como servicio de fondo de la app (cada minuto) en el hilo de la interfaz,
el mismo dueño de la conexión SQLite. Confirma cada mensaje por separado: un
fallo a medias no reenvía lo ya entregado.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

logger = logging.getLogger("spj.products.whatsapp_outbox")

#: Minutos de espera antes de cada reintento (8 intentos ≈ 8 horas).
BACKOFF_MINUTES = (1, 2, 5, 10, 30, 60, 120, 240)
MAX_ATTEMPTS = len(BACKOFF_MINUTES)


def _now() -> datetime:
    return datetime.now(timezone.utc)


class ProductWhatsAppOutboxDispatcher:
    def __init__(self, connection, *, client=None, clock=_now) -> None:
        self._conn = connection
        self._client = client
        self._clock = clock

    def _sender(self):
        if self._client is None:
            from backend.infrastructure.integrations.whatsapp_client import WhatsAppClient
            self._client = WhatsAppClient(connection=self._conn)
        return self._client

    def run_once(self, *, limit: int = 20) -> dict:
        try:
            exists = self._conn.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' "
                "AND name='product_whatsapp_outbox'").fetchone()
        except Exception:
            return {"sent": 0, "retry": 0, "failed": 0}
        if exists is None:
            return {"sent": 0, "retry": 0, "failed": 0}
        now = self._clock()
        due = self._conn.execute(
            "SELECT id, phone, message, attempts FROM product_whatsapp_outbox "
            "WHERE status='PENDING' AND next_attempt_at <= ? "
            "ORDER BY next_attempt_at LIMIT ?",
            (now.isoformat(timespec="seconds"), int(limit))).fetchall()
        outcome = {"sent": 0, "retry": 0, "failed": 0}
        for message_id, phone, body, attempts in due:
            error = None
            try:
                delivered = bool(self._sender().enviar_mensaje(phone, body))
                if not delivered:
                    error = "El servicio de WhatsApp no confirmó el envío"
            except Exception as exc:  # red caída, servicio apagado: se reintenta
                delivered, error = False, str(exc) or exc.__class__.__name__
            attempts = int(attempts) + 1
            if delivered:
                self._conn.execute(
                    "UPDATE product_whatsapp_outbox SET status='SENT', attempts=?, "
                    "sent_at=?, last_error=NULL WHERE id=?",
                    (attempts, now.isoformat(timespec="seconds"), message_id))
                outcome["sent"] += 1
            elif attempts >= MAX_ATTEMPTS:
                self._conn.execute(
                    "UPDATE product_whatsapp_outbox SET status='FAILED', attempts=?, "
                    "last_error=? WHERE id=?", (attempts, error, message_id))
                outcome["failed"] += 1
            else:
                wait = timedelta(minutes=BACKOFF_MINUTES[attempts - 1])
                self._conn.execute(
                    "UPDATE product_whatsapp_outbox SET attempts=?, last_error=?, "
                    "next_attempt_at=? WHERE id=?",
                    (attempts, error, (now + wait).isoformat(timespec="seconds"), message_id))
                outcome["retry"] += 1
            self._conn.commit()
        if due:
            logger.info("Cola de WhatsApp de Productos: %s", outcome)
        return outcome
