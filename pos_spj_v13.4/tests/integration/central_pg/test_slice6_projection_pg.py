"""Caja, Finanzas, Crédito y Fidelidad de punta a punta contra PostgreSQL REAL
(Slice 6; CI `central-postgres`).

La caja (SQLite) produce sus hechos por casos de uso reales, los manda por la
API central y se verifican las vistas de conciliación: balanza cuadrada, saldo
por cobrar del cliente, exposición de crédito, saldo de puntos y movimientos de
caja con signo.
"""

from __future__ import annotations

import os
import random
import uuid
from decimal import Decimal

import pytest

psycopg = pytest.importorskip("psycopg")
DSN = os.environ.get("SPJ_TEST_PG_DSN", "")
pytestmark = pytest.mark.skipif(not DSN, reason="sin PostgreSQL de prueba (SPJ_TEST_PG_DSN)")

import migrations.engine as engine  # noqa: E402
from backend.infrastructure.db.database import (  # noqa: E402
    DatabaseSettings,
    create_connection_factory,
)
from backend.shared.ids import new_uuid  # noqa: E402


@pytest.fixture
def conectar():
    nombre = f"t_{uuid.uuid4().hex[:12]}"
    base = create_connection_factory(DatabaseSettings.postgresql(DSN))
    c = base()
    with c.cursor() as cur:
        cur.execute(f"CREATE SCHEMA {nombre}")
        cur.execute(f"SET search_path TO {nombre}")
    c.commit()
    engine.up_postgresql(c)
    c.close()

    def abrir():
        x = base()
        with x.cursor() as cur:
            cur.execute(f"SET search_path TO {nombre}")
        x.commit()
        return x

    yield abrir
    c = base()
    with c.cursor() as cur:
        cur.execute(f"DROP SCHEMA {nombre} CASCADE")
    c.commit()
    c.close()


def _uno(conn, sql, params=()):
    with conn.cursor() as cur:
        cur.execute(sql, params)
        return cur.fetchone()


def test_cash_finance_credit_and_loyalty_reconcile_centrally(conectar):
    from fastapi.testclient import TestClient

    from backend.api.central_app import CentralSyncWorkflow, create_central_app
    from backend.application.sync.replication_outbox import ReplicationOutboxService
    from backend.application.sync.station_admin import CentralStationAdmin
    from backend.infrastructure.central.projection_repository import (
        PostgresCentralProjectionRepository,
    )
    from backend.infrastructure.central.sync_inbox_repository import (
        PostgresCentralInboxRepository,
    )
    from backend.infrastructure.sync.http_transport import HttpReplicationTransport
    from tests.integration.central_pg.slice6_station import build_station

    pg = conectar()
    emitida = CentralStationAdmin(PostgresCentralInboxRepository(pg)).register(
        station_id=new_uuid(), branch_id=new_uuid())
    pg.close()
    caja, ids = build_station(emitida.station_id, emitida.branch_id)
    app = create_central_app(CentralSyncWorkflow(conectar, PostgresCentralInboxRepository,
                                                 PostgresCentralProjectionRepository))
    motor = ReplicationOutboxService(HttpReplicationTransport(
        "http://testserver", station_id=emitida.station_id, secret=emitida.secret,
        client=TestClient(app, base_url="http://testserver"), allow_insecure_localhost=True),
        rng=random.Random(2))
    resultado = motor.synchronize(caja, station_id=emitida.station_id)
    assert (resultado.synced, resultado.dead) == (9, 0), resultado

    pg = conectar()
    errores = _uno(pg, "SELECT count(*) FROM central_projection_log WHERE status='ERROR'")[0]
    assert errores == 0
    # Finanzas: la balanza central cuadra y el cliente debe $100.
    debe, haber = _uno(pg, "SELECT SUM(debits), SUM(credits) FROM central_trial_balance")
    assert debe == haber == Decimal("100.00")
    assert _uno(pg, "SELECT balance FROM central_receivables WHERE customer_id=%s",
                (ids["customer_id"],))[0] == Decimal("100.00")
    # Crédito: exposición consolidada = límite − por cobrar.
    limite, por_cobrar, disponible = _uno(
        pg, "SELECT credit_limit, receivable, available FROM central_credit_exposure"
            " WHERE customer_id=%s", (ids["customer_id"],))
    assert (limite, por_cobrar, disponible) == (Decimal("5000.00"), Decimal("100.00"),
                                                Decimal("4900.00"))
    # Fidelidad: 100 ganados − 30 canjeados (la confirmación no resta dos veces).
    assert _uno(pg, "SELECT points FROM central_loyalty_balances WHERE customer_id=%s",
                (ids["customer_id"],))[0] == Decimal("70")
    # Caja: entrada +150, retiro a caja fuerte −100; corte con su diferencia.
    assert _uno(pg, "SELECT SUM(signed_amount) FROM central_cash_movements WHERE shift_id=%s",
                (ids["shift_id"],))[0] == Decimal("50.00")
    assert _uno(pg, "SELECT difference FROM central_cash_cuts WHERE shift_id=%s",
                (ids["shift_id"],))[0] == Decimal("-0.50")
    assert _uno(pg, "SELECT opening_amount, status FROM central_cash_shifts WHERE shift_id=%s",
                (ids["shift_id"],)) == (Decimal("500.00"), "OPEN")
    pg.close()
    caja.close()


def test_an_unbalanced_entry_cannot_enter_the_central_ledger(conectar):
    """La base misma rechaza un asiento cuyo debe ≠ haber (CHECK), además del
    traductor: una corrección financiera nunca entra en silencio. (PostgreSQL
    evalúa el CHECK antes que las llaves foráneas.)"""
    pg = conectar()
    with pytest.raises(psycopg.errors.CheckViolation):
        with pg.cursor() as cur:
            cur.execute("INSERT INTO central_journal_entries (entry_id, event_id, branch_id,"
                        " entry_number, entry_date, posting_date, currency_code,"
                        " base_currency_code, total_debits, total_credits, occurred_at)"
                        " VALUES (%s,%s,%s,'X',current_date,current_date,'MXN','MXN',100,99,now())",
                        (new_uuid(), new_uuid(), new_uuid()))
    pg.rollback()
    pg.close()
