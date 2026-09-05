# tests/test_whatsapp_schema.py — WA-3
"""Esquema limpio del canal WhatsApp: UUIDv7, constraints, inbox, outbox,
idempotencia, dead letter — contra SQLite real, no mockeado."""
from __future__ import annotations

import importlib
import sqlite3

import pytest

from backend.infrastructure.db.schema.whatsapp_schema import (
    WHATSAPP_TABLES,
    create_whatsapp_schema,
    drop_whatsapp_schema,
)


@pytest.fixture()
def conn():
    connection = sqlite3.connect(":memory:")
    create_whatsapp_schema(connection)
    yield connection
    connection.close()


def _columns(connection, table):
    return {row[1]: row for row in connection.execute(f"PRAGMA table_info({table})").fetchall()}


def _pk_type(connection, table):
    for row in connection.execute(f"PRAGMA table_info({table})").fetchall():
        # row: (cid, name, type, notnull, dflt_value, pk)
        if row[5] == 1:
            return row[2]
    return None


class TestSchemaCreation:
    def test_all_tables_created(self, conn):
        existing = {
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
        assert set(WHATSAPP_TABLES).issubset(existing)
        # WA-3: 12. WA-10 (migración 244) agregó whatsapp_order_drafts +
        # whatsapp_order_draft_lines -> 14. WA-11 (migración 245) agregó
        # whatsapp_quote_drafts + whatsapp_quote_draft_lines -> 16. WA-13
        # (migración 246) agregó whatsapp_delivery_requests -> 17. WA-16
        # (migración 247) agregó whatsapp_handoff_requests -> 18.
        assert len(WHATSAPP_TABLES) == 18

    def test_create_is_idempotent(self, conn):
        create_whatsapp_schema(conn)  # segunda vez, no debe fallar
        create_whatsapp_schema(conn)

    @pytest.mark.parametrize("table", WHATSAPP_TABLES)
    def test_every_table_has_text_primary_key(self, conn, table):
        assert _pk_type(conn, table) == "TEXT"

    def test_drop_removes_all_tables(self, conn):
        dropped = drop_whatsapp_schema(conn)
        assert set(dropped) == set(WHATSAPP_TABLES)
        remaining = {
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
        assert not remaining.intersection(WHATSAPP_TABLES)


class TestNoCollisionWithLegacyTables:
    """§75 del prompt maestro: nombres canónicos nuevos, ninguno reemplaza
    una tabla legacy existente (docs/refactor/whatsapp_schema_consolidation.md)."""

    LEGACY_TABLE_NAMES = {
        "whatsapp_numeros",
        "wa_event_log",
        "wa_business_idempotency",
        "wa_reminder_queue",
        "whatsapp_queue",
        "wa_message_queue",
        "bot_sessions",
        "bot_mensajes_log",
        "rasa_sessions",
        "pedidos_whatsapp",
        "pedidos_whatsapp_items",
        "conversations",
        "message_log",
        "marketing_messages",
        "notification_inbox",
    }

    def test_no_canonical_name_matches_a_legacy_name(self):
        assert not set(WHATSAPP_TABLES).intersection(self.LEGACY_TABLE_NAMES)


class TestConstraints:
    def test_business_account_external_id_is_unique(self, conn):
        conn.execute(
            "INSERT INTO whatsapp_business_accounts "
            "(id, provider, business_account_external_id, display_name, status, "
            "secret_reference_id, created_at, updated_at) "
            "VALUES ('acc-1','META','ext-1','SPJ','DRAFT',NULL,'t','t')"
        )
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                "INSERT INTO whatsapp_business_accounts "
                "(id, provider, business_account_external_id, display_name, status, "
                "secret_reference_id, created_at, updated_at) "
                "VALUES ('acc-2','META','ext-1','Otro','DRAFT',NULL,'t','t')"
            )

    def test_channel_number_phone_number_external_id_is_unique(self, conn):
        _seed_account(conn)
        conn.execute(_insert_number_sql(), ("num-1", "acc-1", "ext-num-1"))
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(_insert_number_sql(), ("num-2", "acc-1", "ext-num-1"))

    def test_message_delivery_message_id_is_unique(self, conn):
        _seed_full_conversation(conn)
        conn.execute(
            "INSERT INTO whatsapp_messages "
            "(id, conversation_id, direction, message_type, created_at) "
            "VALUES ('msg-1','conv-1','INBOUND','TEXT','t')"
        )
        conn.execute(
            "INSERT INTO whatsapp_message_deliveries "
            "(id, message_id, status, attempt_count, updated_at) "
            "VALUES ('del-1','msg-1','QUEUED',0,'t')"
        )
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                "INSERT INTO whatsapp_message_deliveries "
                "(id, message_id, status, attempt_count, updated_at) "
                "VALUES ('del-2','msg-1','QUEUED',0,'t')"
            )

    def test_idempotency_operation_id_and_fingerprint_are_unique(self, conn):
        conn.execute(
            "INSERT INTO whatsapp_business_operation_idempotency "
            "(id, operation_id, operation_type, aggregate_type, aggregate_id, "
            "fingerprint, status, created_at) "
            "VALUES ('idem-1','op-1','CREATE_ORDER','ORDER','order-1','fp-1','PENDING','t')"
        )
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                "INSERT INTO whatsapp_business_operation_idempotency "
                "(id, operation_id, operation_type, aggregate_type, aggregate_id, "
                "fingerprint, status, created_at) "
                "VALUES ('idem-2','op-1','CREATE_ORDER','ORDER','order-2','fp-2','PENDING','t')"
            )
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                "INSERT INTO whatsapp_business_operation_idempotency "
                "(id, operation_id, operation_type, aggregate_type, aggregate_id, "
                "fingerprint, status, created_at) "
                "VALUES ('idem-3','op-2','CREATE_ORDER','ORDER','order-3','fp-1','PENDING','t')"
            )

    def test_outbox_operation_id_is_unique_when_present(self, conn):
        conn.execute(
            "INSERT INTO whatsapp_outbox "
            "(id, destination_phone, payload_json, operation_id, status, created_at) "
            "VALUES ('ob-1','+525512345678','{}','op-1','PENDING','t')"
        )
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                "INSERT INTO whatsapp_outbox "
                "(id, destination_phone, payload_json, operation_id, status, created_at) "
                "VALUES ('ob-2','+525512345678','{}','op-1','PENDING','t')"
            )

    def test_outbox_allows_multiple_rows_without_operation_id(self, conn):
        conn.execute(
            "INSERT INTO whatsapp_outbox "
            "(id, destination_phone, payload_json, operation_id, status, created_at) "
            "VALUES ('ob-1','+525512345678','{}',NULL,'PENDING','t')"
        )
        conn.execute(
            "INSERT INTO whatsapp_outbox "
            "(id, destination_phone, payload_json, operation_id, status, created_at) "
            "VALUES ('ob-2','+525512345678','{}',NULL,'PENDING','t')"
        )  # dos NULL no violan UNIQUE en SQLite — no debe lanzar


class TestDomainEntityRoundTrip:
    """Round-trip real: una entidad de dominio WA-2 se inserta contra el
    esquema WA-3 con sus propios campos, sin adaptar nada a mano — prueba
    que el esquema realmente encaja con lo que el dominio produce."""

    def test_business_account_round_trips(self, conn):
        from domain.whatsapp.entities.business_account import WhatsAppBusinessAccount
        from domain.whatsapp.enums import WhatsAppProvider

        account = WhatsAppBusinessAccount.create(
            provider=WhatsAppProvider.META,
            business_account_external_id="ext-123",
            display_name="SPJ Carnicería",
        )
        conn.execute(
            "INSERT INTO whatsapp_business_accounts "
            "(id, provider, business_account_external_id, display_name, status, "
            "secret_reference_id, created_at, updated_at) VALUES (?,?,?,?,?,?,?,?)",
            (
                account.id,
                account.provider.value,
                account.business_account_external_id,
                account.display_name,
                account.status.value,
                account.secret_reference_id,
                account.created_at.isoformat(),
                account.updated_at.isoformat(),
            ),
        )
        row = conn.execute(
            "SELECT id, business_account_external_id, status FROM whatsapp_business_accounts WHERE id=?",
            (account.id,),
        ).fetchone()
        assert row == (account.id, "ext-123", "DRAFT")

    def test_channel_number_round_trips(self, conn):
        from domain.whatsapp.entities.channel_number import WhatsAppChannelNumber
        from domain.whatsapp.enums import ChannelRole

        _seed_account(conn)
        number = WhatsAppChannelNumber.create(
            account_id="acc-1",
            phone_number_external_id="ext-num-9",
            display_phone_number="5512345678",
            channel_role=ChannelRole.BRANCH_SALES,
            branch_id="branch-1",
        )
        conn.execute(
            _insert_number_sql(full=True),
            (
                number.id,
                number.account_id,
                number.phone_number_external_id,
                number.display_phone_number,
                number.normalized_phone_number.value,
                number.branch_id,
                number.channel_role.value,
                number.status.value,
                number.timezone,
                number.locale,
                number.created_at.isoformat(),
                number.updated_at.isoformat(),
            ),
        )
        row = conn.execute(
            "SELECT normalized_phone_number, channel_role FROM whatsapp_channel_numbers WHERE id=?",
            (number.id,),
        ).fetchone()
        assert row == ("+525512345678", "BRANCH_SALES")

    def test_conversation_and_message_delivery_transition_round_trip(self, conn):
        from domain.whatsapp.entities.conversation import WhatsAppConversation
        from domain.whatsapp.entities.message import WhatsAppMessage, WhatsAppMessageDelivery
        from domain.whatsapp.enums import ConversationState, MessageDeliveryStatus, MessageDirection, MessageType

        _seed_account(conn)
        conn.execute(_insert_number_sql(), ("num-1", "acc-1", "ext-num-1"))
        conn.execute(
            "INSERT INTO whatsapp_identities "
            "(id, wa_id, normalized_phone, identity_status, first_seen_at, last_seen_at, "
            "created_at, updated_at) VALUES ('identity-1','wa-ext-1','+525512345678','UNRESOLVED','t','t','t','t')"
        )

        conversation = WhatsAppConversation.open(
            identity_id="identity-1", channel_number_id="num-1", branch_id="branch-1"
        )
        conversation.transition_to(ConversationState.BOT_ACTIVE)
        conn.execute(
            "INSERT INTO whatsapp_conversations "
            "(id, identity_id, channel_number_id, branch_id, state, context_json, "
            "context_version, opened_at, updated_at) VALUES (?,?,?,?,?,?,?,?,?)",
            (
                conversation.id,
                conversation.identity_id,
                conversation.channel_number_id,
                conversation.branch_id,
                conversation.state.value,
                "{}",
                conversation.context.version,
                conversation.opened_at.isoformat(),
                conversation.updated_at.isoformat(),
            ),
        )

        message = WhatsAppMessage.create(
            conversation_id=conversation.id,
            direction=MessageDirection.OUTBOUND,
            message_type=MessageType.TEMPLATE,
        )
        conn.execute(
            "INSERT INTO whatsapp_messages (id, conversation_id, direction, message_type, created_at) "
            "VALUES (?,?,?,?,?)",
            (message.id, message.conversation_id, message.direction.value, message.message_type.value,
             message.created_at.isoformat()),
        )

        delivery = WhatsAppMessageDelivery.create(message_id=message.id)
        delivery.transition_to(MessageDeliveryStatus.SENT)
        conn.execute(
            "INSERT INTO whatsapp_message_deliveries "
            "(id, message_id, status, sent_at, attempt_count, updated_at) VALUES (?,?,?,?,?,?)",
            (delivery.id, delivery.message_id, delivery.status.value,
             delivery.sent_at.isoformat(), delivery.attempt_count, delivery.updated_at.isoformat()),
        )

        row = conn.execute(
            "SELECT status, attempt_count FROM whatsapp_message_deliveries WHERE id=?", (delivery.id,)
        ).fetchone()
        assert row == ("SENT", 1)


class TestMigrationWrapper:
    def test_migration_243_delegates_and_commits(self):
        module = importlib.import_module(
            "migrations.standalone.243_whatsapp_bounded_context_schema"
        )
        connection = sqlite3.connect(":memory:")
        try:
            module.run(connection)
            tables = {
                row[0]
                for row in connection.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                ).fetchall()
            }
            assert set(WHATSAPP_TABLES).issubset(tables)
        finally:
            connection.close()

    def test_migration_244_delegates_and_commits(self):
        module = importlib.import_module(
            "migrations.standalone.244_whatsapp_order_drafts_schema"
        )
        connection = sqlite3.connect(":memory:")
        try:
            module.run(connection)
            tables = {
                row[0]
                for row in connection.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                ).fetchall()
            }
            assert {"whatsapp_order_drafts", "whatsapp_order_draft_lines"}.issubset(tables)
        finally:
            connection.close()

    def test_migration_245_delegates_and_commits(self):
        module = importlib.import_module(
            "migrations.standalone.245_whatsapp_quote_drafts_schema"
        )
        connection = sqlite3.connect(":memory:")
        try:
            module.run(connection)
            tables = {
                row[0]
                for row in connection.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                ).fetchall()
            }
            assert {"whatsapp_quote_drafts", "whatsapp_quote_draft_lines"}.issubset(tables)
        finally:
            connection.close()

    def test_migration_246_delegates_and_commits(self):
        module = importlib.import_module(
            "migrations.standalone.246_whatsapp_delivery_requests_schema"
        )
        connection = sqlite3.connect(":memory:")
        try:
            module.run(connection)
            tables = {
                row[0]
                for row in connection.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                ).fetchall()
            }
            assert "whatsapp_delivery_requests" in tables
        finally:
            connection.close()

    def test_migration_247_delegates_and_commits(self):
        module = importlib.import_module(
            "migrations.standalone.247_whatsapp_handoff_requests_schema"
        )
        connection = sqlite3.connect(":memory:")
        try:
            module.run(connection)
            tables = {
                row[0]
                for row in connection.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                ).fetchall()
            }
            assert "whatsapp_handoff_requests" in tables
        finally:
            connection.close()

    def test_migration_243_is_registered_in_engine(self):
        from migrations.engine import MIGRATIONS

        versions = [m.version for m in MIGRATIONS]
        assert "243" in versions
        # WA-10/11/13/16 agregaron migraciones después — 243 ya no es la
        # última, pero sigue registrada en orden.
        assert (
            versions.index("243") < versions.index("244") < versions.index("245")
            < versions.index("246") < versions.index("247")
        )


def _seed_account(conn, account_id="acc-1"):
    conn.execute(
        "INSERT INTO whatsapp_business_accounts "
        "(id, provider, business_account_external_id, display_name, status, "
        "secret_reference_id, created_at, updated_at) "
        f"VALUES ('{account_id}','META','ext-{account_id}','SPJ','DRAFT',NULL,'t','t')"
    )


def _seed_full_conversation(conn):
    _seed_account(conn)
    conn.execute(_insert_number_sql(), ("num-1", "acc-1", "ext-num-1"))
    conn.execute(
        "INSERT INTO whatsapp_identities "
        "(id, wa_id, normalized_phone, identity_status, first_seen_at, last_seen_at, "
        "created_at, updated_at) VALUES ('identity-1','wa-ext-1','+525512345678','UNRESOLVED','t','t','t','t')"
    )
    conn.execute(
        "INSERT INTO whatsapp_conversations "
        "(id, identity_id, channel_number_id, state, context_json, context_version, opened_at, updated_at) "
        "VALUES ('conv-1','identity-1','num-1','OPEN','{}',1,'t','t')"
    )


def _insert_number_sql(full: bool = False) -> str:
    if full:
        return (
            "INSERT INTO whatsapp_channel_numbers "
            "(id, account_id, phone_number_external_id, display_phone_number, "
            "normalized_phone_number, branch_id, channel_role, status, timezone, locale, "
            "created_at, updated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)"
        )
    return (
        "INSERT INTO whatsapp_channel_numbers "
        "(id, account_id, phone_number_external_id, display_phone_number, "
        "normalized_phone_number, branch_id, channel_role, status, timezone, locale, "
        "created_at, updated_at) "
        "VALUES (?,?,?,'5512345678','+525512345678','branch-1','BRANCH_SALES','DRAFT','America/Mexico_City','es-MX','t','t')"
    )
