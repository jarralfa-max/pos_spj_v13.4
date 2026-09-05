# tests/test_consent_service.py — WA-14
"""`ConsentService` — verifica el puente `clientes.id` (legacy) ->
`customers.id` (Customer Master, CRM-3) contra el esquema REAL de ambos
bounded contexts (mismo patrón de fixture que
`tests/integration/customers/conftest.py::full_crm_conn`), con un
`ConsentApiClient` falso (el contrato de WA-14, no su implementación)."""
from __future__ import annotations

import asyncio
import sqlite3

import pytest

from application.consent_service import ConsentService
from backend.infrastructure.db.schema.customers_crm_schema import create_customers_crm_schema


class _FakeConsentClient:
    def __init__(self):
        self.grant_calls = []
        self.opt_out_calls = []
        self._status = {}

    async def get_status(self, customer_id):
        return self._status.get(customer_id)

    async def grant(self, customer_id, *, evidence_reference):
        self.grant_calls.append((customer_id, evidence_reference))
        self._status[customer_id] = "GRANTED"

    async def opt_out(self, customer_id, *, reason):
        self.opt_out_calls.append((customer_id, reason))
        self._status[customer_id] = "WITHDRAWN"


class _FakeRoot:
    def __init__(self, conn, *, consent=None):
        self.connection = conn
        self.consent = consent or _FakeConsentClient()


@pytest.fixture()
def conn():
    connection = sqlite3.connect(":memory:")
    create_customers_crm_schema(connection)
    connection.execute(
        "CREATE TABLE clientes (id TEXT PRIMARY KEY, nombre TEXT, telefono TEXT, activo INTEGER DEFAULT 1)"
    )
    connection.execute("INSERT INTO clientes (id, nombre, telefono) VALUES ('legacy-1', 'Juan Pérez', '+525512345678')")
    connection.commit()
    yield connection
    connection.close()


def _run(coro):
    return asyncio.run(coro)


class TestLegacyBridging:
    def test_grant_resolves_legacy_id_to_customer_master_id(self, conn):
        consent = _FakeConsentClient()
        service = ConsentService(_FakeRoot(conn, consent=consent))

        _run(service.record_opt_in(customer_external_id="legacy-1", evidence_reference="checkbox WA"))

        assert len(consent.grant_calls) == 1
        bridged_id, evidence = consent.grant_calls[0]
        assert bridged_id != "legacy-1"  # nunca el id legacy crudo
        assert evidence == "checkbox WA"

        row = conn.execute(
            "SELECT id FROM customers WHERE legacy_customer_id=?", ("legacy-1",)
        ).fetchone()
        assert row is not None
        assert row[0] == bridged_id

    def test_same_legacy_customer_resolves_to_the_same_bridged_id_twice(self, conn):
        consent = _FakeConsentClient()
        service = ConsentService(_FakeRoot(conn, consent=consent))

        _run(service.record_opt_in(customer_external_id="legacy-1", evidence_reference="a"))
        _run(service.record_opt_out(customer_external_id="legacy-1", reason="b"))

        first_id = consent.grant_calls[0][0]
        second_id = consent.opt_out_calls[0][0]
        assert first_id == second_id


class TestOptOutAndStatus:
    def test_is_opted_out_reflects_withdrawn_status(self, conn):
        consent = _FakeConsentClient()
        service = ConsentService(_FakeRoot(conn, consent=consent))

        assert _run(service.is_opted_out(customer_external_id="legacy-1")) is False
        _run(service.record_opt_out(customer_external_id="legacy-1", reason="BAJA"))
        assert _run(service.is_opted_out(customer_external_id="legacy-1")) is True
