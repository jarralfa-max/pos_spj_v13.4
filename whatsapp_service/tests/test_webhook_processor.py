# tests/test_webhook_processor.py — WA-6
from __future__ import annotations

import sqlite3
from datetime import datetime

import pytest

from backend.infrastructure.db.schema.whatsapp_schema import create_whatsapp_schema
from bootstrap.composition_root import WhatsAppCompositionRoot
from domain.whatsapp.entities.business_account import WhatsAppBusinessAccount
from domain.whatsapp.entities.channel_number import WhatsAppChannelNumber
from domain.whatsapp.enums import ChannelRole, WhatsAppProvider
from domain.whatsapp.exceptions import ChannelNumberNotRegisteredError
from models.message import IncomingMessage, InteractiveType, MessageType


@pytest.fixture()
def root():
    connection = sqlite3.connect(":memory:")
    create_whatsapp_schema(connection)
    r = WhatsAppCompositionRoot(connection)
    yield r
    connection.close()


@pytest.fixture()
def registered_number(root):
    account = WhatsAppBusinessAccount.create(
        provider=WhatsAppProvider.META, business_account_external_id="acc-ext-1", display_name="SPJ"
    )
    root.accounts.save(account)
    number = WhatsAppChannelNumber.create(
        account_id=account.id,
        phone_number_external_id="phone-ext-1",
        display_phone_number="5500000000",
        channel_role=ChannelRole.BRANCH_SALES,
        branch_id="branch-1",
    )
    root.numbers.save(number)
    return number


def _incoming(**overrides) -> IncomingMessage:
    defaults = dict(
        message_id="wamid.1",
        from_number="5512345678",
        phone_number_id="phone-ext-1",
        timestamp=datetime.now(),
        type=MessageType.TEXT,
        text="hola",
    )
    defaults.update(overrides)
    return IncomingMessage(**defaults)


class TestWebhookProcessorHappyPath:
    def test_creates_identity_conversation_message_and_job(self, root, registered_number):
        result = root.webhook_processor.process(_incoming())
        assert result.deduplicated is False
        assert result.message_id is not None
        assert result.conversation_id is not None
        assert result.inbox_job_id is not None

        message = root.messages.get_by_id(result.message_id)
        assert message.provider_message_id == "wamid.1"

        conversation = root.conversations.get_by_id(result.conversation_id)
        assert conversation.identity_id is not None
        assert conversation.channel_number_id == registered_number.id

        identity = root.identities.get_by_wa_id("5512345678")
        assert identity is not None

        job = root.inbox.get_by_message_id(result.message_id)
        assert job.id == result.inbox_job_id

    def test_second_message_reuses_open_conversation(self, root, registered_number):
        first = root.webhook_processor.process(_incoming(message_id="wamid.1"))
        second = root.webhook_processor.process(_incoming(message_id="wamid.2"))
        assert second.conversation_id == first.conversation_id

    def test_second_message_reuses_existing_identity(self, root, registered_number):
        root.webhook_processor.process(_incoming(message_id="wamid.1"))
        root.webhook_processor.process(_incoming(message_id="wamid.2"))
        # No debe crear una segunda identidad para el mismo wa_id.
        identity = root.identities.get_by_wa_id("5512345678")
        assert identity is not None

    def test_interactive_button_reply_maps_to_button_reply_type(self, root, registered_number):
        from domain.whatsapp.enums import MessageType as DomainMessageType

        incoming = _incoming(
            type=MessageType.INTERACTIVE,
            interactive_type=InteractiveType.BUTTON_REPLY,
            interactive_id="menu_pedido",
        )
        result = root.webhook_processor.process(incoming)
        message = root.messages.get_by_id(result.message_id)
        assert message.message_type == DomainMessageType.BUTTON_REPLY


class TestWebhookProcessorDedupe:
    def test_same_provider_message_id_is_deduplicated(self, root, registered_number):
        first = root.webhook_processor.process(_incoming(message_id="wamid.dup"))
        second = root.webhook_processor.process(_incoming(message_id="wamid.dup"))
        assert second.deduplicated is True
        assert second.message_id == first.message_id
        assert second.inbox_job_id is None

    def test_dedupe_does_not_create_a_second_inbox_job(self, root, registered_number):
        root.webhook_processor.process(_incoming(message_id="wamid.dup"))
        root.webhook_processor.process(_incoming(message_id="wamid.dup"))
        count = root.registry.get("whatsapp_db_connection").execute(
            "SELECT COUNT(*) FROM whatsapp_inbox"
        ).fetchone()[0]
        assert count == 1


class TestWebhookProcessorUnregisteredNumber:
    def test_raises_channel_number_not_registered(self, root):
        with pytest.raises(ChannelNumberNotRegisteredError):
            root.webhook_processor.process(_incoming(phone_number_id="never-registered"))
