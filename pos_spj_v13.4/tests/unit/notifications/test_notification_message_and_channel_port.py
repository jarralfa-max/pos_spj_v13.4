"""SET-20 — "Channels": NotificationMessage + NotificationChannelPort
composition. A Protocol with no real implementation in this bounded
context (see notification_channel_ports.py's docstring — real senders
already exist per-module and aren't duplicated/imported here); this test
proves the shape works end to end with a fake channel, mirroring
tests/unit/document_output/test_rendering_ports_composition.py's pattern.
"""

from __future__ import annotations

import pytest

from backend.domain.notifications.enums import NotificationChannel
from backend.domain.notifications.exceptions import NotificationsInvalidValueError
from backend.domain.notifications.notification_channel_ports import NotificationChannelPort
from backend.domain.notifications.value_objects.notification_message import NotificationMessage
from backend.shared.ids import new_uuid


class _FakeChannel:
    """Satisfies NotificationChannelPort structurally — no real provider."""

    def __init__(self) -> None:
        self.sent: list[NotificationMessage] = []

    def send(self, message: NotificationMessage) -> str:
        self.sent.append(message)
        return f"delivery-{len(self.sent)}"


class _FailingChannel:
    def send(self, message: NotificationMessage) -> str:
        raise ConnectionError("proveedor no disponible")


class TestNotificationMessageCreate:
    def test_requires_body(self):
        with pytest.raises(NotificationsInvalidValueError):
            NotificationMessage.create(channel=NotificationChannel.EMAIL, recipient="a@b.com", body="   ")

    @pytest.mark.parametrize("channel", [NotificationChannel.WHATSAPP, NotificationChannel.SMS])
    def test_phone_addressed_channels_require_e164(self, channel):
        with pytest.raises(NotificationsInvalidValueError):
            NotificationMessage.create(channel=channel, recipient="5512345678", body="hola")

    @pytest.mark.parametrize("channel", [NotificationChannel.WHATSAPP, NotificationChannel.SMS])
    def test_phone_addressed_channels_accept_valid_e164(self, channel):
        message = NotificationMessage.create(channel=channel, recipient="+525512345678", body="hola")
        assert message.recipient == "+525512345678"

    def test_email_requires_at_sign(self):
        with pytest.raises(NotificationsInvalidValueError):
            NotificationMessage.create(channel=NotificationChannel.EMAIL, recipient="not-an-email", body="hola")

    def test_email_accepts_valid_address(self):
        message = NotificationMessage.create(
            channel=NotificationChannel.EMAIL, recipient="cliente@example.com", body="hola",
        )
        assert message.recipient == "cliente@example.com"

    def test_push_requires_non_blank_recipient(self):
        with pytest.raises(NotificationsInvalidValueError):
            NotificationMessage.create(channel=NotificationChannel.PUSH, recipient="   ", body="hola")

    def test_push_accepts_a_device_token(self):
        message = NotificationMessage.create(channel=NotificationChannel.PUSH, recipient="device-token-123", body="hola")
        assert message.recipient == "device-token-123"

    def test_title_defaults_to_empty(self):
        message = NotificationMessage.create(channel=NotificationChannel.EMAIL, recipient="a@b.com", body="hola")
        assert message.title == ""


class TestNotificationChannelPortComposition:
    def test_fake_channel_records_sent_message_and_returns_delivery_id(self):
        channel: NotificationChannelPort = _FakeChannel()
        message = NotificationMessage.create(
            channel=NotificationChannel.WHATSAPP, recipient="+525512345678", body="Tu pedido está confirmado",
            operation_id=new_uuid(),
        )
        delivery_id = channel.send(message)
        assert delivery_id == "delivery-1"
        assert channel.sent == [message]

    def test_channel_failure_propagates(self):
        channel: NotificationChannelPort = _FailingChannel()
        message = NotificationMessage.create(channel=NotificationChannel.EMAIL, recipient="a@b.com", body="hola")
        with pytest.raises(ConnectionError):
            channel.send(message)
