"""CRM-31 — el envío de WhatsApp honra un consentimiento WITHDRAWN
explícito del Customer Master; nunca bloquea por ausencia de registro."""
import sys
from pathlib import Path
import sqlite3

# Mismo orden que test_bridge_create_cliente_minimo.py (CRM-25): el path
# del ERP debe insertarse PRIMERO, el de whatsapp_service SEGUNDO, porque
# `sys.path.insert(0, X)` siempre gana sobre un insert(0, ...) anterior y
# `config/` (paquete real de whatsapp_service) debe resolver antes que el
# `config.py` de un solo archivo del ERP.
ERP_ROOT = Path(__file__).resolve().parents[2] / "pos_spj_v13.4"
sys.path.insert(0, str(ERP_ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest

from messaging.sender import _is_whatsapp_opted_out
from models.message import OutgoingMessage
import messaging.sender as sender_mod


def _erp_db(tmp_path) -> str:
    from backend.infrastructure.db.schema.customers_crm_schema import create_customers_crm_schema
    from backend.infrastructure.db.schema.customer_privacy_schema import create_customer_privacy_schema

    dbp = tmp_path / "erp.db"
    conn = sqlite3.connect(dbp)
    conn.execute(
        "CREATE TABLE clientes (id TEXT PRIMARY KEY, nombre TEXT, telefono TEXT, activo INTEGER DEFAULT 1)"
    )
    create_customers_crm_schema(conn)
    conn.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_customers_legacy_customer_id"
        " ON customers(legacy_customer_id) WHERE legacy_customer_id IS NOT NULL"
    )
    create_customer_privacy_schema(conn)
    conn.commit()
    conn.close()
    return str(dbp)


def _make_cliente(db_path: str, *, phone: str) -> str:
    conn = sqlite3.connect(db_path)
    from backend.shared.ids import new_uuid
    cid = new_uuid()
    conn.execute(
        "INSERT INTO clientes (id, nombre, telefono, activo) VALUES (?, 'Cliente Test', ?, 1)",
        (cid, phone),
    )
    conn.commit()
    conn.close()
    return cid


def _withdraw_whatsapp_consent(db_path: str, legacy_cliente_id: str) -> None:
    from backend.application.customers.use_cases.legacy_customer_bridge_use_cases import (
        ResolveLegacyCustomerUseCase,
    )
    from backend.shared.ids import new_uuid
    from datetime import datetime, timezone

    conn = sqlite3.connect(db_path)
    customer_id = ResolveLegacyCustomerUseCase().execute(conn, legacy_customer_id=legacy_cliente_id)
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    conn.execute(
        "INSERT INTO customer_consents (id, customer_id, consent_type, status, withdrawn_at,"
        " withdrawal_reason, created_at, updated_at)"
        " VALUES (?, ?, 'WHATSAPP', 'WITHDRAWN', ?, 'usuario solicitó baja', ?, ?)",
        (new_uuid(), customer_id, now, now, now),
    )
    conn.commit()
    conn.close()


@pytest.fixture(autouse=True)
def _point_sender_at_db(tmp_path, monkeypatch):
    db_path = _erp_db(tmp_path)
    monkeypatch.setattr(sender_mod, "ERP_DB_PATH", db_path)
    return db_path


def test_no_consent_record_never_blocks(_point_sender_at_db):
    db_path = _point_sender_at_db
    _make_cliente(db_path, phone="5551234567")
    assert _is_whatsapp_opted_out("5551234567") is False


def test_unknown_phone_never_blocks(_point_sender_at_db):
    assert _is_whatsapp_opted_out("5559999999") is False


def test_withdrawn_consent_blocks(_point_sender_at_db):
    db_path = _point_sender_at_db
    cid = _make_cliente(db_path, phone="5557778888")
    _withdraw_whatsapp_consent(db_path, cid)
    assert _is_whatsapp_opted_out("5557778888") is True


def test_granted_consent_does_not_block(_point_sender_at_db):
    from backend.application.customers.use_cases.legacy_customer_bridge_use_cases import (
        ResolveLegacyCustomerUseCase,
    )
    from backend.shared.ids import new_uuid
    from datetime import datetime, timezone

    db_path = _point_sender_at_db
    cid = _make_cliente(db_path, phone="5550001111")
    conn = sqlite3.connect(db_path)
    customer_id = ResolveLegacyCustomerUseCase().execute(conn, legacy_customer_id=cid)
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    conn.execute(
        "INSERT INTO customer_consents (id, customer_id, consent_type, status, granted_at,"
        " evidence_reference, created_at, updated_at)"
        " VALUES (?, ?, 'WHATSAPP', 'GRANTED', ?, 'checkbox web', ?, ?)",
        (new_uuid(), customer_id, now, now, now),
    )
    conn.commit()
    conn.close()

    assert _is_whatsapp_opted_out("5550001111") is False


def test_send_message_returns_false_when_opted_out(_point_sender_at_db, monkeypatch):
    import asyncio

    db_path = _point_sender_at_db
    cid = _make_cliente(db_path, phone="5552223333")
    _withdraw_whatsapp_consent(db_path, cid)

    called = {"n": 0}

    def _boom(*a, **k):
        called["n"] += 1
        raise AssertionError("no debió intentar obtener config tras el bloqueo por consentimiento")

    monkeypatch.setattr(sender_mod, "_get_whatsapp_config", _boom)

    ok = asyncio.run(sender_mod.send_message(OutgoingMessage(to="5552223333", text="hola")))

    assert ok is False
    assert called["n"] == 0
