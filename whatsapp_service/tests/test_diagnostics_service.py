# tests/test_diagnostics_service.py — WA-20
from __future__ import annotations

import sqlite3
import uuid
from datetime import datetime, timedelta, timezone

import pytest

from application.diagnostics_service import DiagnosticsService
from backend.infrastructure.db.schema.whatsapp_schema import create_whatsapp_schema


def _uuid() -> str:
    return str(uuid.uuid4())


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class _FakeRegistry:
    def __init__(self, conn):
        self._conn = conn

    def get(self, name):
        assert name == "whatsapp_db_connection"
        return self._conn


class _FakeRoot:
    def __init__(self, conn):
        self.registry = _FakeRegistry(conn)


@pytest.fixture()
def conn():
    connection = sqlite3.connect(":memory:")
    create_whatsapp_schema(connection)
    yield connection
    connection.close()


@pytest.fixture()
def service(conn):
    return DiagnosticsService(_FakeRoot(conn))


class TestEmptyChannel:
    def test_returns_zeros_not_errors(self, service):
        metrics = service.get_metrics()
        assert metrics["conversations"]["total"] == 0
        assert metrics["messages"]["total"] == 0
        assert metrics["inbox"]["pending"] == 0
        assert metrics["outbox"]["pending"] == 0
        assert metrics["dead_letter"]["unresolved"] == 0
        assert metrics["handoff"]["by_status"] == {}


class TestConversationsAndMessages:
    def test_counts_by_state_and_direction(self, conn, service):
        conn.execute(
            "INSERT INTO whatsapp_business_accounts "
            "(id, provider, business_account_external_id, display_name, status, created_at, updated_at) "
            "VALUES (?,'META',?,'SPJ','ACTIVE',?,?)",
            (_uuid(), _uuid(), _now(), _now()),
        )
        account_id = conn.execute("SELECT id FROM whatsapp_business_accounts").fetchone()[0]
        number_id = _uuid()
        conn.execute(
            "INSERT INTO whatsapp_channel_numbers "
            "(id, account_id, phone_number_external_id, display_phone_number, normalized_phone_number, "
            "channel_role, status, timezone, locale, created_at, updated_at) "
            "VALUES (?,?,?,?,?,'GLOBAL_CUSTOMER_SERVICE','ACTIVE','America/Mexico_City','es_MX',?,?)",
            (number_id, account_id, _uuid(), "+525512345678", "+525512345678", _now(), _now()),
        )
        identity_id = _uuid()
        conn.execute(
            "INSERT INTO whatsapp_identities "
            "(id, wa_id, normalized_phone, identity_status, first_seen_at, last_seen_at, created_at, updated_at) "
            "VALUES (?,?,?,'RESOLVED',?,?,?,?)",
            (identity_id, _uuid(), "+525512345678", _now(), _now(), _now(), _now()),
        )
        conv_open, conv_resolved = _uuid(), _uuid()
        conn.execute(
            "INSERT INTO whatsapp_conversations "
            "(id, identity_id, channel_number_id, state, context_json, context_version, opened_at, updated_at) "
            "VALUES (?,?,?,'OPEN','{}',1,?,?)",
            (conv_open, identity_id, number_id, _now(), _now()),
        )
        conn.execute(
            "INSERT INTO whatsapp_conversations "
            "(id, identity_id, channel_number_id, state, context_json, context_version, opened_at, updated_at) "
            "VALUES (?,?,?,'RESOLVED','{}',1,?,?)",
            (conv_resolved, identity_id, number_id, _now(), _now()),
        )
        conn.execute(
            "INSERT INTO whatsapp_messages (id, conversation_id, direction, message_type, created_at) "
            "VALUES (?,?,'INBOUND','TEXT',?)", (_uuid(), conv_open, _now()),
        )
        conn.execute(
            "INSERT INTO whatsapp_messages (id, conversation_id, direction, message_type, created_at) "
            "VALUES (?,?,'OUTBOUND','TEXT',?)", (_uuid(), conv_open, _now()),
        )
        conn.commit()

        metrics = service.get_metrics()
        assert metrics["conversations"]["total"] == 2
        assert metrics["conversations"]["by_state"] == {"OPEN": 1, "RESOLVED": 1}
        assert metrics["messages"]["total"] == 2
        assert metrics["messages"]["today"] == 2
        assert metrics["messages"]["by_direction"] == {"INBOUND": 1, "OUTBOUND": 1}


class TestQueues:
    def test_outbox_pending_and_age(self, conn, service):
        old = (datetime.now(timezone.utc) - timedelta(minutes=10)).isoformat()
        conn.execute(
            "INSERT INTO whatsapp_outbox (id, destination_phone, payload_json, status, attempts, created_at) "
            "VALUES (?,?,?,'PENDING',0,?)", (_uuid(), "+525512345678", "{}", old),
        )
        conn.execute(
            "INSERT INTO whatsapp_outbox (id, destination_phone, payload_json, status, attempts, created_at) "
            "VALUES (?,?,?,'SENT',1,?)", (_uuid(), "+525512345678", "{}", _now()),
        )
        conn.commit()

        metrics = service.get_metrics()
        assert metrics["outbox"]["pending"] == 1
        assert metrics["outbox"]["oldest_pending_age_seconds"] >= 590

    def test_inbox_counts_pending_and_retry(self, conn, service):
        conn.execute(
            "INSERT INTO whatsapp_messages (id, conversation_id, direction, message_type, created_at) "
            "VALUES (?,?,'INBOUND','TEXT',?)", (_uuid(), _uuid(), _now()),
        )
        message_id = conn.execute("SELECT id FROM whatsapp_messages").fetchone()[0]
        conn.execute(
            "INSERT INTO whatsapp_inbox (id, message_id, status, attempts, created_at) "
            "VALUES (?,?,'RETRY',1,?)", (_uuid(), message_id, _now()),
        )
        conn.commit()

        assert service.get_metrics()["inbox"]["pending"] == 1


class TestDeadLetterHandoffIdempotency:
    def test_dead_letter_unresolved_vs_total(self, conn, service):
        conn.execute(
            "INSERT INTO whatsapp_dead_letter (id, failure_type, attempts, created_at, resolved_at) "
            "VALUES (?,?,3,?,NULL)", (_uuid(), "SEND_FAILED", _now()),
        )
        conn.execute(
            "INSERT INTO whatsapp_dead_letter (id, failure_type, attempts, created_at, resolved_at) "
            "VALUES (?,?,3,?,?)", (_uuid(), "SEND_FAILED", _now(), _now()),
        )
        conn.commit()

        metrics = service.get_metrics()
        assert metrics["dead_letter"]["total"] == 2
        assert metrics["dead_letter"]["unresolved"] == 1

    def test_handoff_by_status_and_oldest_open_age(self, conn, service):
        old = (datetime.now(timezone.utc) - timedelta(minutes=5)).isoformat()
        conn.execute(
            "INSERT INTO whatsapp_handoff_requests (id, conversation_id, reason, status, created_at, updated_at) "
            "VALUES (?,?,?,?,?,?)", (_uuid(), _uuid(), "motivo", "OPEN", old, old),
        )
        conn.commit()

        metrics = service.get_metrics()
        assert metrics["handoff"]["by_status"] == {"OPEN": 1}
        assert metrics["handoff"]["oldest_open_age_seconds"] >= 290

    def test_idempotency_by_status_and_operation_type(self, conn, service):
        conn.execute(
            "INSERT INTO whatsapp_business_operation_idempotency "
            "(id, operation_id, operation_type, aggregate_type, fingerprint, status, created_at) "
            "VALUES (?,?,'CREATE_ORDER','ORDER_DRAFT',?,'COMPLETED',?)",
            (_uuid(), _uuid(), _uuid(), _now()),
        )
        conn.execute(
            "INSERT INTO whatsapp_business_operation_idempotency "
            "(id, operation_id, operation_type, aggregate_type, fingerprint, status, created_at) "
            "VALUES (?,?,'CONFIRM_PAYMENT','ORDER',?,'FAILED',?)",
            (_uuid(), _uuid(), _uuid(), _now()),
        )
        conn.commit()

        metrics = service.get_metrics()
        assert metrics["idempotency"]["by_status"] == {"COMPLETED": 1, "FAILED": 1}
        assert metrics["idempotency"]["by_operation_type"] == {"CREATE_ORDER": 1, "CONFIRM_PAYMENT": 1}


class TestDegradesGracefully:
    def test_missing_tables_do_not_raise(self):
        connection = sqlite3.connect(":memory:")
        service = DiagnosticsService(_FakeRoot(connection))
        metrics = service.get_metrics()
        assert metrics["conversations"]["total"] == 0
        assert metrics["outbox"]["oldest_pending_age_seconds"] is None
        connection.close()
