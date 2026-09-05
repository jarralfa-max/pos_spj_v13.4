# tests/test_consent_client.py — WA-14
"""`CustomerConsentApiClient` contra el esquema REAL de Customer Privacy
(CRM-9, `customer_consents`) — no un doble/fake del repositorio."""
from __future__ import annotations

import asyncio
import sqlite3

import pytest

from backend.infrastructure.db.schema.customer_privacy_schema import create_customer_privacy_schema
from infrastructure.erp_clients.consent_client import CustomerConsentApiClient


@pytest.fixture()
def conn():
    connection = sqlite3.connect(":memory:")
    create_customer_privacy_schema(connection)
    yield connection
    connection.close()


@pytest.fixture()
def client(conn):
    return CustomerConsentApiClient(conn)


def _run(coro):
    return asyncio.run(coro)


class TestGetStatus:
    def test_returns_none_when_never_captured(self, client):
        assert _run(client.get_status("cust-1")) is None

    def test_returns_granted_after_grant(self, client):
        _run(client.grant("cust-1", evidence_reference="checkbox onboarding WA"))
        assert _run(client.get_status("cust-1")) == "GRANTED"


class TestGrant:
    def test_grant_persists_a_granted_record(self, client, conn):
        _run(client.grant("cust-1", evidence_reference="respuesta SI"))
        row = conn.execute(
            "SELECT status, channel, evidence_reference FROM customer_consents WHERE customer_id=?",
            ("cust-1",),
        ).fetchone()
        assert row == ("GRANTED", "WHATSAPP", "respuesta SI")


class TestOptOut:
    def test_opt_out_without_prior_grant_creates_withdrawn_record(self, client):
        """El caso real de WA-14: un cliente responde "BAJA" la primera
        vez que escribe, sin haber otorgado consentimiento antes."""
        _run(client.opt_out("cust-1", reason="Cliente escribió BAJA"))
        assert _run(client.get_status("cust-1")) == "WITHDRAWN"

    def test_opt_out_withdraws_an_existing_grant(self, client):
        _run(client.grant("cust-1", evidence_reference="respuesta SI"))
        _run(client.opt_out("cust-1", reason="Cliente escribió BAJA"))
        assert _run(client.get_status("cust-1")) == "WITHDRAWN"

    def test_opt_out_is_idempotent(self, client, conn):
        _run(client.opt_out("cust-1", reason="Cliente escribió BAJA"))
        _run(client.opt_out("cust-1", reason="Cliente escribió BAJA otra vez"))
        count = conn.execute(
            "SELECT COUNT(*) FROM customer_consents WHERE customer_id=?", ("cust-1",)
        ).fetchone()[0]
        assert count == 1

    def test_opt_in_after_opt_out_grants_again(self, client):
        _run(client.opt_out("cust-1", reason="Cliente escribió BAJA"))
        _run(client.grant("cust-1", evidence_reference="Cliente pidió reactivar"))
        assert _run(client.get_status("cust-1")) == "GRANTED"
