# tests/test_sqlite_whatsapp_repositories.py — WA-4
"""Round-trip real de los 6 repositorios SQLite contra el esquema de WA-3
— cada test guarda una entidad de dominio real (construida con sus propios
`create()`/métodos de transición de WA-2) y la relee, verificando que
sobrevive intacta, incluidos los value objects y enums."""
from __future__ import annotations

import sqlite3

import pytest

from backend.infrastructure.db.schema.whatsapp_schema import create_whatsapp_schema
from domain.whatsapp.entities.business_account import (
    WhatsAppBusinessAccount,
    WhatsAppProviderConfiguration,
)
from domain.whatsapp.entities.channel_number import WhatsAppChannelNumber
from domain.whatsapp.entities.conversation import ConversationSession, WhatsAppConversation
from domain.whatsapp.entities.identity import WhatsAppIdentity
from domain.whatsapp.entities.message import WhatsAppMessage, WhatsAppMessageDelivery
from domain.whatsapp.enums import (
    ChannelRole,
    ConversationState,
    MessageDeliveryStatus,
    MessageDirection,
    MessageType,
    WhatsAppProvider,
)
from infrastructure.persistence.sqlite_account_repository import (
    SqliteWhatsAppAccountRepository,
    SqliteWhatsAppProviderConfigurationRepository,
)
from infrastructure.persistence.sqlite_conversation_repository import (
    SqliteWhatsAppConversationRepository,
)
from infrastructure.persistence.sqlite_identity_repository import SqliteWhatsAppIdentityRepository
from infrastructure.persistence.sqlite_message_repository import SqliteWhatsAppMessageRepository
from infrastructure.persistence.sqlite_number_repository import SqliteWhatsAppNumberRepository


@pytest.fixture()
def conn():
    connection = sqlite3.connect(":memory:")
    create_whatsapp_schema(connection)
    yield connection
    connection.close()


class TestAccountRepository:
    def test_save_and_get_by_id(self, conn):
        repo = SqliteWhatsAppAccountRepository(conn)
        account = WhatsAppBusinessAccount.create(
            provider=WhatsAppProvider.META,
            business_account_external_id="ext-1",
            display_name="SPJ",
        )
        repo.save(account)
        fetched = repo.get_by_id(account.id)
        assert fetched.id == account.id
        assert fetched.provider == WhatsAppProvider.META
        assert fetched.status == account.status

    def test_get_by_external_id(self, conn):
        repo = SqliteWhatsAppAccountRepository(conn)
        account = WhatsAppBusinessAccount.create(
            provider=WhatsAppProvider.META, business_account_external_id="ext-9", display_name="SPJ"
        )
        repo.save(account)
        assert repo.get_by_external_id("ext-9").id == account.id

    def test_get_by_id_missing_returns_none(self, conn):
        repo = SqliteWhatsAppAccountRepository(conn)
        assert repo.get_by_id("does-not-exist") is None

    def test_save_twice_upserts_status_change(self, conn):
        repo = SqliteWhatsAppAccountRepository(conn)
        account = WhatsAppBusinessAccount.create(
            provider=WhatsAppProvider.META, business_account_external_id="ext-2", display_name="SPJ"
        )
        repo.save(account)
        account.activate()
        repo.save(account)
        fetched = repo.get_by_id(account.id)
        assert fetched.status.value == "ACTIVE"

    def test_list_active_excludes_draft(self, conn):
        repo = SqliteWhatsAppAccountRepository(conn)
        draft = WhatsAppBusinessAccount.create(
            provider=WhatsAppProvider.META, business_account_external_id="ext-draft", display_name="D"
        )
        active = WhatsAppBusinessAccount.create(
            provider=WhatsAppProvider.META, business_account_external_id="ext-active", display_name="A"
        )
        active.activate()
        repo.save(draft)
        repo.save(active)
        ids = {a.id for a in repo.list_active()}
        assert active.id in ids
        assert draft.id not in ids


class TestProviderConfigurationRepository:
    def test_save_and_get_by_account_id(self, conn):
        repo = SqliteWhatsAppProviderConfigurationRepository(conn)
        config = WhatsAppProviderConfiguration.create(
            account_id="acc-1",
            provider=WhatsAppProvider.META,
            api_version="v21.0",
            extra_settings={"foo": "bar"},
        )
        repo.save(config)
        fetched = repo.get_by_account_id("acc-1")
        assert fetched.api_version == "v21.0"
        assert fetched.extra_settings == {"foo": "bar"}


class TestNumberRepository:
    def _number(self):
        return WhatsAppChannelNumber.create(
            account_id="acc-1",
            phone_number_external_id="ext-num-1",
            display_phone_number="5512345678",
            channel_role=ChannelRole.BRANCH_SALES,
            branch_id="branch-1",
        )

    def test_save_and_get_by_id_preserves_normalized_phone(self, conn):
        repo = SqliteWhatsAppNumberRepository(conn)
        number = self._number()
        repo.save(number)
        fetched = repo.get_by_id(number.id)
        assert fetched.normalized_phone_number.value == "+525512345678"
        assert fetched.channel_role == ChannelRole.BRANCH_SALES

    def test_get_by_external_id(self, conn):
        repo = SqliteWhatsAppNumberRepository(conn)
        number = self._number()
        repo.save(number)
        assert repo.get_by_external_id("ext-num-1").id == number.id

    def test_get_by_branch(self, conn):
        repo = SqliteWhatsAppNumberRepository(conn)
        number = self._number()
        repo.save(number)
        results = repo.get_by_branch("branch-1")
        assert [n.id for n in results] == [number.id]

    def test_get_global_numbers(self, conn):
        repo = SqliteWhatsAppNumberRepository(conn)
        global_number = WhatsAppChannelNumber.create(
            account_id="acc-1",
            phone_number_external_id="ext-global",
            display_phone_number="5500000000",
            channel_role=ChannelRole.GLOBAL_CUSTOMER_SERVICE,
        )
        repo.save(self._number())
        repo.save(global_number)
        results = repo.get_global_numbers()
        assert [n.id for n in results] == [global_number.id]


class TestIdentityRepository:
    def test_save_and_get_by_wa_id(self, conn):
        repo = SqliteWhatsAppIdentityRepository(conn)
        identity = WhatsAppIdentity.create(wa_id="wa-ext-1", raw_phone="5512345678")
        repo.save(identity)
        fetched = repo.get_by_wa_id("wa-ext-1")
        assert fetched.id == identity.id
        assert fetched.normalized_phone.value == "+525512345678"

    def test_get_by_normalized_phone(self, conn):
        repo = SqliteWhatsAppIdentityRepository(conn)
        identity = WhatsAppIdentity.create(wa_id="wa-ext-2", raw_phone="5512345678")
        repo.save(identity)
        assert repo.get_by_normalized_phone("+525512345678").id == identity.id

    def test_save_twice_upserts_link_to_customer(self, conn):
        repo = SqliteWhatsAppIdentityRepository(conn)
        identity = WhatsAppIdentity.create(wa_id="wa-ext-3", raw_phone="5512345678")
        repo.save(identity)
        identity.link_to_customer("cust-1")
        repo.save(identity)
        fetched = repo.get_by_id(identity.id)
        assert fetched.customer_id == "cust-1"
        assert fetched.identity_status.value == "RESOLVED"


class TestConversationRepository:
    def test_save_and_get_by_id_round_trips_context(self, conn):
        repo = SqliteWhatsAppConversationRepository(conn)
        conversation = WhatsAppConversation.open(
            identity_id="identity-1", channel_number_id="number-1", branch_id="branch-1"
        )
        conversation.update_context(active_order_draft_id="order-1")
        repo.save(conversation)
        fetched = repo.get_by_id(conversation.id)
        assert fetched.context.active_order_draft_id == "order-1"
        assert fetched.context.branch_id == "branch-1"
        assert fetched.context.version == conversation.context.version

    def test_save_twice_upserts_state_transition(self, conn):
        repo = SqliteWhatsAppConversationRepository(conn)
        conversation = WhatsAppConversation.open(identity_id="identity-1", channel_number_id="number-1")
        repo.save(conversation)
        conversation.transition_to(ConversationState.BOT_ACTIVE)
        repo.save(conversation)
        fetched = repo.get_by_id(conversation.id)
        assert fetched.state == ConversationState.BOT_ACTIVE

    def test_get_open_for_identity_ignores_closed(self, conn):
        repo = SqliteWhatsAppConversationRepository(conn)
        closed = WhatsAppConversation.open(identity_id="identity-1", channel_number_id="number-1")
        closed.transition_to(ConversationState.CLOSED)
        repo.save(closed)
        open_conv = WhatsAppConversation.open(identity_id="identity-1", channel_number_id="number-1")
        repo.save(open_conv)
        fetched = repo.get_open_for_identity("identity-1", "number-1")
        assert fetched.id == open_conv.id

    def test_save_session(self, conn):
        repo = SqliteWhatsAppConversationRepository(conn)
        conversation = WhatsAppConversation.open(identity_id="identity-1", channel_number_id="number-1")
        repo.save(conversation)
        session = ConversationSession.start(conversation_id=conversation.id)
        repo.save_session(session)  # no debe lanzar
        session.end()
        repo.save_session(session)  # upsert ended_at, no debe lanzar


class TestMessageRepository:
    def _message(self, conversation_id="conv-1"):
        return WhatsAppMessage.create(
            conversation_id=conversation_id,
            direction=MessageDirection.INBOUND,
            message_type=MessageType.TEXT,
            provider_message_id="wamid.123",
        )

    def test_save_and_get_by_id(self, conn):
        repo = SqliteWhatsAppMessageRepository(conn)
        message = self._message()
        repo.save(message)
        fetched = repo.get_by_id(message.id)
        assert fetched.provider_message_id == "wamid.123"
        assert fetched.direction == MessageDirection.INBOUND

    def test_get_by_provider_message_id(self, conn):
        repo = SqliteWhatsAppMessageRepository(conn)
        message = self._message()
        repo.save(message)
        assert repo.get_by_provider_message_id("wamid.123").id == message.id

    def test_delivery_round_trip_with_transition(self, conn):
        repo = SqliteWhatsAppMessageRepository(conn)
        message = self._message()
        repo.save(message)
        delivery = WhatsAppMessageDelivery.create(message_id=message.id)
        delivery.transition_to(MessageDeliveryStatus.SENT)
        repo.save_delivery(delivery)

        fetched = repo.get_delivery_for_message(message.id)
        assert fetched.status == MessageDeliveryStatus.SENT
        assert fetched.attempt_count == 1
        assert fetched.sent_at is not None

    def test_delivery_upsert_on_further_transition(self, conn):
        repo = SqliteWhatsAppMessageRepository(conn)
        message = self._message()
        repo.save(message)
        delivery = WhatsAppMessageDelivery.create(message_id=message.id)
        delivery.transition_to(MessageDeliveryStatus.SENT)
        repo.save_delivery(delivery)
        delivery.transition_to(MessageDeliveryStatus.DELIVERED)
        repo.save_delivery(delivery)

        fetched = repo.get_delivery(delivery.id)
        assert fetched.status == MessageDeliveryStatus.DELIVERED
        assert fetched.delivered_at is not None
