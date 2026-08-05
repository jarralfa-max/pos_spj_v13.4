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
