# tests/test_loyalty_client.py — WA-15
"""`LoyaltySnapshotApiClient` contra la misma forma de tabla
`loyalty_snapshots` que ya usa `LoyaltyCustomerSummaryQuery` (CRM-21)."""
from __future__ import annotations

import asyncio
import sqlite3

import pytest

from infrastructure.erp_clients.loyalty_client import LoyaltySnapshotApiClient


@pytest.fixture()
def conn():
    connection = sqlite3.connect(":memory:")
    connection.execute(
        "CREATE TABLE loyalty_snapshots (id TEXT PRIMARY KEY, cliente_id TEXT UNIQUE, "
        "puntos_actuales INTEGER DEFAULT 0, nivel TEXT DEFAULT 'Bronce', visitas INTEGER DEFAULT 0, "
        "importe_total REAL DEFAULT 0)"
    )
    connection.commit()
    yield connection
    connection.close()


@pytest.fixture()
def client(conn):
    return LoyaltySnapshotApiClient(conn)


def _run(coro):
    return asyncio.run(coro)


class TestGetSummary:
    def test_returns_not_enrolled_when_no_snapshot_row(self, client):
        summary = _run(client.get_summary("cliente-1"))
        assert summary.enrolled is False
        assert summary.points == 0
        assert summary.tier == ""

    def test_returns_real_snapshot_values(self, client, conn):
        conn.execute(
            "INSERT INTO loyalty_snapshots (id, cliente_id, puntos_actuales, nivel, visitas) "
            "VALUES ('snap-1','cliente-1', 340, 'Oro', 12)"
        )
        conn.commit()

        summary = _run(client.get_summary("cliente-1"))
        assert summary.enrolled is True
        assert summary.points == 340
        assert summary.tier == "Oro"
        assert summary.visits == 12

    def test_never_reads_other_customers_snapshot(self, client, conn):
        conn.execute(
            "INSERT INTO loyalty_snapshots (id, cliente_id, puntos_actuales) VALUES ('snap-2','otro-cliente', 999)"
        )
        conn.commit()

        summary = _run(client.get_summary("cliente-1"))
        assert summary.enrolled is False
