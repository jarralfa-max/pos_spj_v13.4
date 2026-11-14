"""Avisos al cliente de Pedidos sobre `whatsapp_outbox` (SDLC-ORD-006).

Medido: cada aviso ("va en camino", "entregado", "no pudimos entregar",
"listo para recoger", "requiere tu aprobación") era una sola llamada HTTP al
microservicio. Si fallaba, un warning en el log y el cliente nunca se enteraba.

Ahora:

1. `enqueue` guarda el aviso en `whatsapp_outbox` DENTRO de la transacción del
   hecho que lo causa (decisión del responsable: esa cola, no una tercera).
   Es idempotente por `operation_id`: un reintento de la operación no duplica el
   aviso.
2. `deliver` lo intenta en cuanto la transacción confirma. Así `notification_sent`
   sigue diciendo si salió.
3. `drain` (tarea de fondo del shell) reintenta lo pendiente con espera
   creciente. Al agotar `MAX_ATTEMPTS` lo deja en `DEAD_LETTER` y avisa a
   gerencia de la sucursal en su bandeja.

El `payload_json` lleva `kind="text"` y `body`, la forma que entiende el
`OutboundDispatcher` del microservicio. `source="orders_delivery"` distingue
estos avisos. OJO: hoy ningún proceso del microservicio drena esta tabla
(SDLC-WA-006). Cuando lo haga, este drenado del ERP debe retirarse para no
enviar dos veces (SDLC-WA-037 decide la ruta ERP→canal).

Sin la tabla (una base sin la migración 243) se envía directo, como antes, y se
registra el error: el aviso no se pierde por eso, pero tampoco se reintenta.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

from backend.domain.orders_delivery.policies.notification_policy import (
    NOTICE_FAILED_ALERT_TYPE,
)
from backend.infrastructure.integrations.orders_delivery_internal_notifier import (
    OrdersDeliveryInternalNotifier,
)
from backend.infrastructure.integrations.orders_delivery_whatsapp_client import (
    OrdersDeliveryWhatsAppClient,
)
from backend.shared.ids import new_uuid

logger = logging.getLogger("spj.orders_delivery.notice_outbox")

SOURCE = "orders_delivery"


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(momento: datetime) -> str:
    return momento.isoformat(timespec="seconds")


@dataclass(frozen=True)
class Notice:
    """Un aviso por entregar. `message_id` es None si no hubo cola (se envía directo)."""
    route: str
    phone: str
    fields: dict = field(default_factory=dict)
    message_id: str | None = None


class OrdersDeliveryNoticeOutbox:
    MAX_ATTEMPTS = 5
    #: Espera entre intentos: 30 s, 60 s, 120 s… con tope de una hora.
    BASE_DELAY_SECONDS = 30
    MAX_DELAY_SECONDS = 3600

    def __init__(self, connection, *, whatsapp: OrdersDeliveryWhatsAppClient | None = None,
                 internal_notifier_factory=OrdersDeliveryInternalNotifier) -> None:
        self._conn = connection
        self._whatsapp = whatsapp or OrdersDeliveryWhatsAppClient()
        self._notifier_factory = internal_notifier_factory

    # ── encolar (en la transacción de quien llama) ───────────────────────
    def enqueue(self, *, route: str, phone: str, operation_id: str, branch_id: str,
                order_id: str, **fields) -> Notice | None:
        phone = (phone or "").strip()
        if not phone:
            return None
        aviso = Notice(route=route, phone=phone, fields=dict(fields))
        if not self._has_table():
            logger.error("whatsapp_outbox no existe: el aviso del pedido %s se envía sin "
                         "reintento", order_id)
            return aviso
        clave = f"{operation_id}:aviso"
        previo = self._conn.execute(
            "SELECT id FROM whatsapp_outbox WHERE operation_id=?", (clave,)).fetchone()
        if previo is not None:
            return Notice(route, phone, dict(fields), previo[0])
        message_id = new_uuid()
        payload = {"kind": "text", "body": self._body(route, fields), "source": SOURCE,
                   "route": route, "branch_id": branch_id, "order_id": order_id, **fields}
        self._conn.execute(
            "INSERT INTO whatsapp_outbox (id, destination_phone, payload_json, operation_id,"
            " status, attempts, created_at) VALUES (?,?,?,?, 'PENDING', 0, ?)",
            (message_id, phone, json.dumps(payload, ensure_ascii=False), clave, _iso(_now())))
        return Notice(route, phone, dict(fields), message_id)

    # ── entregar ─────────────────────────────────────────────────────────
    def deliver(self, notice: Notice | None) -> bool:
        """Primer intento, después de confirmar la transacción. Nunca lanza."""
        if notice is None:
            return False
        if notice.message_id is None:
            return self._send(notice.route, notice.phone, notice.fields)
        return self._attempt(notice.message_id)

    def drain(self, *, limit: int = 50) -> dict:
        """Reintenta los avisos de Pedidos pendientes y vencidos."""
        if not self._has_table():
            return {"pending": 0, "sent": 0, "failed": 0}
        filas = self._conn.execute(
            "SELECT id FROM whatsapp_outbox WHERE status='PENDING'"
            " AND json_extract(payload_json, '$.source') = ?"
            " AND (next_retry_at IS NULL OR next_retry_at <= ?)"
            " ORDER BY created_at LIMIT ?", (SOURCE, _iso(_now()), int(limit))).fetchall()
        enviados = sum(1 for (message_id,) in filas if self._attempt(message_id))
        return {"pending": len(filas), "sent": enviados, "failed": len(filas) - enviados}

    def _attempt(self, message_id: str) -> bool:
        fila = self._conn.execute(
            "SELECT destination_phone, payload_json, status, attempts FROM whatsapp_outbox"
            " WHERE id=?", (message_id,)).fetchone()
        if fila is None:
            return False
        phone, payload_json, status, attempts = fila
        if status != "PENDING":
            return status == "SENT"
        datos = json.loads(payload_json)
        enviado, error = False, ""
        try:
            enviado = self._send(datos.get("route", "send"), phone, datos)
            error = "" if enviado else "El microservicio de WhatsApp no confirmó el envío"
        except Exception as exc:  # noqa: BLE001 - el aviso queda para reintento
            error = str(exc) or type(exc).__name__
        intentos = int(attempts or 0) + 1
        if enviado:
            self._conn.execute(
                "UPDATE whatsapp_outbox SET status='SENT', attempts=?, last_error=NULL,"
                " next_retry_at=NULL, processed_at=? WHERE id=?",
                (intentos, _iso(_now()), message_id))
        elif intentos >= self.MAX_ATTEMPTS:
            self._conn.execute(
                "UPDATE whatsapp_outbox SET status='DEAD_LETTER', attempts=?, last_error=?,"
                " next_retry_at=NULL, processed_at=? WHERE id=?",
                (intentos, error, _iso(_now()), message_id))
            self._alert_branch(datos, error)
        else:
            espera = min(self.MAX_DELAY_SECONDS, self.BASE_DELAY_SECONDS * 2 ** (intentos - 1))
            self._conn.execute(
                "UPDATE whatsapp_outbox SET attempts=?, last_error=?, next_retry_at=?"
                " WHERE id=?",
                (intentos, error, _iso(_now() + timedelta(seconds=espera)), message_id))
        self._conn.commit()
        return enviado

    def _alert_branch(self, datos: dict, error: str) -> None:
        folio = datos.get("order_number") or datos.get("order_id") or ""
        self._notifier_factory(self._conn).notify_roles(
            roles=("admin", "gerente"), branch_id=str(datos.get("branch_id") or ""),
            tipo=NOTICE_FAILED_ALERT_TYPE,
            titulo=f"Aviso al cliente no entregado — pedido {folio}",
            cuerpo=f"{datos.get('body', '')} ({error})",
            datos={"order_id": datos.get("order_id")})

    def _send(self, route: str, phone: str, fields: dict) -> bool:
        if route == "pedido_listo":
            return self._whatsapp.notify_ready_for_pickup(
                phone=phone, order_number=fields.get("order_number", ""),
                branch_name=fields.get("branch_name", ""))
        if route == "approval":
            return self._whatsapp.notify_customer_approval_required(
                phone=phone, order_number=fields.get("order_number", ""),
                reason=fields.get("reason", ""))
        return self._whatsapp.send_message(phone=phone, message=fields.get("message", ""))

    @staticmethod
    def _body(route: str, fields: dict) -> str:
        if route == "pedido_listo":
            return f"Tu pedido {fields.get('order_number', '')} está listo para recoger."
        if route == "approval":
            return (f"Hola, tu pedido {fields.get('order_number', '')} requiere tu aprobación: "
                    f"{fields.get('reason', '')}.")
        return fields.get("message", "")

    def _has_table(self) -> bool:
        return self._conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='whatsapp_outbox'"
        ).fetchone() is not None
