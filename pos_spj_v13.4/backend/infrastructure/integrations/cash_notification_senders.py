"""Provider-neutral adapters for Cash Register notification channels."""
from __future__ import annotations

import re
from typing import Protocol

from backend.application.cash_register.notifications import CashNotificationMessage


class WhatsAppClient(Protocol):
    def send_text(self, *, phone_e164: str, text: str,
                  idempotency_key: str) -> str: ...


class EmailClient(Protocol):
    def send_email(self, *, address: str, subject: str, body: str,
                   idempotency_key: str) -> str: ...


class WhatsAppNotificationSender:
    def __init__(self, client: WhatsAppClient) -> None: self._client = client

    def send(self, message: CashNotificationMessage) -> str:
        if not re.fullmatch(r"\+[1-9]\d{7,14}", message.recipient):
            raise ValueError("WhatsApp recipient must use E.164")
        return self._client.send_text(
            phone_e164=message.recipient,
            text=f"{message.title}\n{message.body}",
            idempotency_key=message.job_id,
        )


class EmailNotificationSender:
    def __init__(self, client: EmailClient) -> None: self._client = client

    def send(self, message: CashNotificationMessage) -> str:
        if "@" not in message.recipient:
            raise ValueError("Invalid email recipient")
        return self._client.send_email(
            address=message.recipient, subject=message.title, body=message.body,
            idempotency_key=message.job_id,
        )


class ErpWhatsAppTextClient:
    """`WhatsAppClient` de Caja sobre el cliente que configura Integraciones
    (`wa_base_url` / `wa_internal_api_key`), el mismo que usan Productos y
    Delivery (CASH-26 bloque 2). Hasta hoy la shell nunca inyectaba un cliente
    y los avisos por WhatsApp quedaban en reintento para siempre."""

    def __init__(self, connection) -> None:
        from backend.infrastructure.integrations.whatsapp_client import WhatsAppClient

        self._client = WhatsAppClient(connection=connection)

    def send_text(self, *, phone_e164: str, text: str, idempotency_key: str) -> str:
        if not self._client.enviar_mensaje(phone_e164, text):
            raise ConnectionError("WhatsApp no confirmó el envío")
        return idempotency_key
