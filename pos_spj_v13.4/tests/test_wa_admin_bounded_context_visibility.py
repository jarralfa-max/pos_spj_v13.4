# tests/test_wa_admin_bounded_context_visibility.py — WA-19
"""`WhatsAppHistoryRepository`/`WhatsAppMetricsRepository` (lado ERP,
panel admin `modulos/whatsapp/whatsapp_module.py`) leyendo el bounded
context nuevo del canal (WA-2/WA-3, `whatsapp_service/domain/whatsapp/`)
además de las fuentes legacy — WA-19 cierra el hallazgo de WA-0
(`wa_message_queue` es una tabla fantasma, nunca creada por ninguna
migración) agregando una fuente real, sin quitar ninguna de las
existentes.

No usa la fixture `_make_db()` de `test_wa_repositories.py` (solo monta
tablas legacy) — aquí se monta el esquema real del canal vía
`create_whatsapp_schema()`, la misma función que usan las migraciones
243..247.
"""
from __future__ import annotations

import sqlite3
import uuid
from datetime import datetime, timedelta, timezone

import pytest

from backend.infrastructure.db.schema.whatsapp_schema import create_whatsapp_schema
from core.repositories.whatsapp_history_repository import WhatsAppHistoryRepository
from core.repositories.whatsapp_metrics_repository import WhatsAppMetricsRepository


def _uuid() -> str:
    return str(uuid.uuid4())


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


@pytest.fixture()
def conn():
    connection = sqlite3.connect(":memory:")
    create_whatsapp_schema(connection)
    yield connection
    connection.close()


def _seed_conversation(conn, *, phone="+525512345678", state="OPEN", last_message_at=None):
    account_id, number_id, identity_id, conversation_id = _uuid(), _uuid(), _uuid(), _uuid()
    now = _now()
    conn.execute(
        "INSERT INTO whatsapp_business_accounts "
        "(id, provider, business_account_external_id, display_name, status, created_at, updated_at) "
        "VALUES (?,'META',?,'SPJ','ACTIVE',?,?)",
        (account_id, _uuid(), now, now),
    )
    conn.execute(
        "INSERT INTO whatsapp_channel_numbers "
        "(id, account_id, phone_number_external_id, display_phone_number, normalized_phone_number, "
        "channel_role, status, timezone, locale, created_at, updated_at) "
        "VALUES (?,?,?,?,?,'GLOBAL_CUSTOMER_SERVICE','ACTIVE','America/Mexico_City','es_MX',?,?)",
        (number_id, account_id, _uuid(), phone, phone, now, now),
    )
    conn.execute(
        "INSERT INTO whatsapp_identities "
        "(id, wa_id, normalized_phone, identity_status, first_seen_at, last_seen_at, created_at, updated_at) "
        "VALUES (?,?,?,'RESOLVED',?,?,?,?)",
        (identity_id, _uuid(), phone, now, now, now, now),
    )
    conn.execute(
        "INSERT INTO whatsapp_conversations "
        "(id, identity_id, channel_number_id, state, context_json, context_version, opened_at, "
        "last_message_at, updated_at) VALUES (?,?,?,?,?,?,?,?,?)",
        (conversation_id, identity_id, number_id, state, "{}", 1, now, last_message_at or now, now),
    )
    conn.commit()
    return conversation_id


def _seed_message(conn, conversation_id, *, direction="INBOUND", message_type="TEXT", delivery_status=None):
    message_id = _uuid()
    conn.execute(
        "INSERT INTO whatsapp_messages "
        "(id, conversation_id, direction, message_type, created_at) VALUES (?,?,?,?,?)",
        (message_id, conversation_id, direction, message_type, _now()),
    )
    if delivery_status:
        conn.execute(
            "INSERT INTO whatsapp_message_deliveries "
            "(id, message_id, status, attempt_count, updated_at) VALUES (?,?,?,0,?)",
            (_uuid(), message_id, delivery_status, _now()),
        )
    conn.commit()
    return message_id


class TestHistoryFromBoundedContext:
    def test_empty_channel_falls_through_to_legacy_sources(self, conn):
        """Sin tráfico real todavía (nada wireado al webhook en vivo) —
        la nueva fuente no debe romper el fallback existente."""
        repo = WhatsAppHistoryRepository(conn)
        assert repo.get_history("") == []

    def test_reads_real_message_from_new_schema(self, conn):
        conversation_id = _seed_conversation(conn, phone="+525512345678")
        _seed_message(conn, conversation_id, direction="INBOUND", message_type="TEXT")

        repo = WhatsAppHistoryRepository(conn)
        rows = repo.get_history("")

        assert len(rows) == 1
        assert rows[0]["numero"] == "+525512345678"
        assert rows[0]["direccion"] == "⬇️ Entrada"
        assert "TEXT" in rows[0]["mensaje"]

    def test_search_filters_by_phone(self, conn):
        conv_a = _seed_conversation(conn, phone="+525511111111")
        conv_b = _seed_conversation(conn, phone="+525522222222")
        _seed_message(conn, conv_a)
        _seed_message(conn, conv_b)

        repo = WhatsAppHistoryRepository(conn)
        rows = repo.get_history("5511111111")

        assert len(rows) == 1
        assert rows[0]["numero"] == "+525511111111"

    def test_outbound_message_shows_delivery_status(self, conn):
        conversation_id = _seed_conversation(conn)
        _seed_message(conn, conversation_id, direction="OUTBOUND", delivery_status="DELIVERED")

        repo = WhatsAppHistoryRepository(conn)
        rows = repo.get_history("")

        assert rows[0]["direccion"] == "⬆️ Salida"
        assert rows[0]["estado"] == "DELIVERED"

    def test_does_not_break_when_bounded_context_tables_are_absent(self):
        """Panel admin corriendo contra una BD sin las migraciones 243+
        (entorno viejo) — debe degradar, no reventar."""
        connection = sqlite3.connect(":memory:")
        connection.execute(
            "CREATE TABLE pedidos_whatsapp (id INTEGER PRIMARY KEY, fecha TEXT, "
            "numero_whatsapp TEXT, telefono_cliente TEXT, mensaje TEXT, estado TEXT)"
        )
        connection.commit()
        repo = WhatsAppHistoryRepository(connection)
        assert repo.get_history("") == []
        connection.close()


class TestMetricsFromBoundedContext:
    def test_counts_real_messages_and_active_sessions(self, conn):
        conversation_id = _seed_conversation(
            conn, state="BOT_ACTIVE", last_message_at=_now(),
        )
        _seed_message(conn, conversation_id)
        _seed_message(conn, conversation_id)

        repo = WhatsAppMetricsRepository(conn)
        metrics = repo.get_metrics()

        assert metrics["total_mensajes"] == 2
        assert metrics["mensajes_hoy"] == 2
        assert metrics["sesiones_activas"] == 1

    def test_terminal_conversations_do_not_count_as_active(self, conn):
        conversation_id = _seed_conversation(conn, state="RESOLVED", last_message_at=_now())
        _seed_message(conn, conversation_id)

        repo = WhatsAppMetricsRepository(conn)
        metrics = repo.get_metrics()

        assert metrics["sesiones_activas"] == 0

    def test_stale_conversation_does_not_count_as_active(self, conn):
        stale = (datetime.now(timezone.utc) - timedelta(hours=2)).isoformat()
        _seed_conversation(conn, state="BOT_ACTIVE", last_message_at=stale)

        repo = WhatsAppMetricsRepository(conn)
        metrics = repo.get_metrics()

        assert metrics["sesiones_activas"] == 0

    def test_new_operational_metrics_present_and_zero_when_empty(self, conn):
        repo = WhatsAppMetricsRepository(conn)
        metrics = repo.get_metrics()

        assert metrics["wa_handoff_abiertos"] == 0
        assert metrics["wa_outbox_pendiente"] == 0
        assert metrics["wa_dead_letter"] == 0
        assert metrics["wa_entregas_solicitadas"] == 0
        assert metrics["wa_idempotencia_fallidas"] == 0

    def test_counts_open_handoff_requests(self, conn):
        conn.execute(
            "INSERT INTO whatsapp_handoff_requests "
            "(id, conversation_id, reason, status, created_at, updated_at) "
            "VALUES (?,?,?,'OPEN',?,?)",
            (_uuid(), _uuid(), "motivo", _now(), _now()),
        )
        conn.commit()

        repo = WhatsAppMetricsRepository(conn)
        assert repo.get_metrics()["wa_handoff_abiertos"] == 1

    def test_counts_pending_outbox_messages(self, conn):
        conn.execute(
            "INSERT INTO whatsapp_outbox "
            "(id, destination_phone, payload_json, status, attempts, created_at) "
            "VALUES (?,?,?,'PENDING',0,?)",
            (_uuid(), "+525512345678", "{}", _now()),
        )
        conn.commit()

        repo = WhatsAppMetricsRepository(conn)
        assert repo.get_metrics()["wa_outbox_pendiente"] == 1

    def test_does_not_break_when_bounded_context_tables_are_absent(self):
        connection = sqlite3.connect(":memory:")
        connection.execute(
            "CREATE TABLE pedidos_whatsapp (id INTEGER PRIMARY KEY, fecha TEXT, estado TEXT, total REAL)"
        )
        connection.commit()
        repo = WhatsAppMetricsRepository(connection)
        metrics = repo.get_metrics()
        assert metrics["wa_outbox_pendiente"] == 0
        connection.close()
