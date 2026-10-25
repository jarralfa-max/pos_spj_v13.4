"""Ingesta central y API sobre un PostgreSQL REAL (Slice 4). Corre en el CI
(`central-postgres`); aquí se salta si no hay `SPJ_TEST_PG_DSN`."""

from __future__ import annotations

import json
import os
import random
import sqlite3
import threading
import uuid
import importlib
from datetime import datetime, timezone
from decimal import Decimal

import pytest

psycopg = pytest.importorskip("psycopg")
DSN = os.environ.get("SPJ_TEST_PG_DSN", "")
pytestmark = pytest.mark.skipif(not DSN, reason="sin PostgreSQL de prueba (SPJ_TEST_PG_DSN)")

import migrations.engine as engine  # noqa: E402
from backend.application.sync.central_ingestion import CentralIngestionService  # noqa: E402
from backend.application.sync.station_admin import CentralStationAdmin  # noqa: E402
from backend.infrastructure.central.sync_inbox_repository import (  # noqa: E402
    PostgresCentralInboxRepository,
)
from backend.infrastructure.db.database import (  # noqa: E402
    DatabaseSettings,
    create_connection_factory,
)
from backend.shared.ids import new_uuid  # noqa: E402
from backend.shared.sync.replication_envelope import (  # noqa: E402
    ReplicationEnvelope,
    ReplicationOutcome,
)

T0 = datetime(2026, 10, 25, 12, 0, tzinfo=timezone.utc)


@pytest.fixture
def esquema():
    nombre = f"t_{uuid.uuid4().hex[:12]}"
    base = create_connection_factory(DatabaseSettings.postgresql(DSN))
    conn = base()
    with conn.cursor() as cur:
        cur.execute(f"CREATE SCHEMA {nombre}")
        cur.execute(f"SET search_path TO {nombre}")
    conn.commit()
    engine.up_postgresql(conn)
    conn.close()

    def conectar():
        c = base()
        with c.cursor() as cur:
            cur.execute(f"SET search_path TO {nombre}")
        c.commit()
        return c

    yield conectar
    c = base()
    with c.cursor() as cur:
        cur.execute(f"DROP SCHEMA {nombre} CASCADE")
    c.commit()
    c.close()


@pytest.fixture
def central(esquema):
    conn = esquema()
    repo = PostgresCentralInboxRepository(conn)
    emitida = CentralStationAdmin(repo).register(station_id=new_uuid(), branch_id=new_uuid())
    yield conn, repo, emitida
    conn.close()


def sobre(emitida, *, secuencia=1, agregado=None, version=1, **cambios):
    datos = dict(event_id=new_uuid(), operation_id=new_uuid(), event_type="SALE_COMPLETED",
                 schema_version=1, aggregate_type="sales.sale",
                 aggregate_id=agregado or new_uuid(), aggregate_version=version,
                 branch_id=emitida.branch_id, workstation_id=emitida.station_id,
                 sequence_no=secuencia, occurred_at=T0, actor_id=new_uuid(),
                 payload={"total": Decimal("1250.50")})
    datos.update(cambios)
    return ReplicationEnvelope(**datos)


def _ingesta(repo, emitida, *sobres):
    servicio = CentralIngestionService(repo)
    estacion = servicio.authenticate(emitida.station_id, emitida.secret)
    return list(servicio.ingest(estacion, [s.to_dict() for s in sobres], now=T0).acks)


def _uno(conn, sql, params=()):
    with conn.cursor() as cur:
        cur.execute(sql, params)
        return cur.fetchone()


def test_accepted_duplicate_and_contiguous_sequence(central):
    conn, repo, emitida = central
    a, b = sobre(emitida, secuencia=1), sobre(emitida, secuencia=2)
    assert [x.outcome for x in _ingesta(repo, emitida, a, b)] == [ReplicationOutcome.ACCEPTED] * 2
    assert _ingesta(repo, emitida, a)[0].outcome is ReplicationOutcome.DUPLICATE
    assert _uno(conn, "SELECT count(*) FROM sync_inbox")[0] == 2
    assert _uno(conn, "SELECT last_sequence FROM sync_stations WHERE id=%s",
                (emitida.station_id,))[0] == 2
    payload = _uno(conn, "SELECT payload FROM sync_inbox WHERE event_id=%s", (a.event_id,))[0]
    assert payload == {"total": "1250.50"}


def test_conflicts_are_recorded_never_overwritten(central):
    conn, repo, emitida = central
    original = sobre(emitida, secuencia=1)
    _ingesta(repo, emitida, original)
    alterado = sobre(emitida, secuencia=2, event_id=original.event_id,
                     operation_id=original.operation_id, payload={"total": Decimal("1.00")})
    assert _ingesta(repo, emitida, alterado)[0].error_code == "EVENT_ID_REUSED"
    assert _ingesta(repo, emitida, sobre(emitida, secuencia=1))[0].error_code == "SEQUENCE_REUSED"
    agregado = new_uuid()
    _ingesta(repo, emitida, sobre(emitida, secuencia=3, agregado=agregado, version=2))
    assert _ingesta(repo, emitida, sobre(emitida, secuencia=4, agregado=agregado,
                                         version=1))[0].error_code == "AGGREGATE_VERSION_REGRESSION"
    assert _uno(conn, "SELECT payload FROM sync_inbox WHERE event_id=%s",
                (original.event_id,))[0] == {"total": "1250.50"}
    tipos = {f[0] for f in conn.execute("SELECT kind FROM sync_conflicts").fetchall()}
    assert tipos == {"EVENT_ID_REUSED", "AGGREGATE_VERSION_REGRESSION"}


def test_branch_scope_is_enforced(central):
    conn, repo, emitida = central
    acuse = _ingesta(repo, emitida, sobre(emitida, branch_id=new_uuid()))[0]
    assert acuse.error_code == "BRANCH_SCOPE"
    assert _uno(conn, "SELECT count(*) FROM sync_inbox")[0] == 0


def test_two_concurrent_deliveries_of_the_same_fact_apply_it_once(esquema, central):
    _, _, emitida = central
    s = sobre(emitida)
    resultados, barrera = [], threading.Barrier(2)

    def entregar():
        c = esquema()
        try:
            barrera.wait()
            resultados.append(_ingesta(PostgresCentralInboxRepository(c), emitida, s)[0].outcome)
        finally:
            c.close()

    hilos = [threading.Thread(target=entregar) for _ in range(2)]
    for h in hilos:
        h.start()
    for h in hilos:
        h.join()
    conn = esquema()
    assert _uno(conn, "SELECT count(*) FROM sync_inbox WHERE event_id=%s", (s.event_id,))[0] == 1
    conn.close()
    # Exactamente una entrega lo aplica; la otra lo reconoce como duplicado.
    assert sorted(r.value for r in resultados) == ["ACCEPTED", "DUPLICATE"]


def test_from_the_till_to_postgresql_through_the_real_api(esquema, central):
    """SQLite de la caja → motor → HTTPS (TestClient) → API → PostgreSQL."""
    from fastapi.testclient import TestClient

    from backend.api.central_app import CentralSyncWorkflow, create_central_app
    from backend.application.sync.replication_outbox import ReplicationOutboxService
    from backend.domain.cash_register.events import CashEvents, cash_event_payload
    from backend.infrastructure.db.repositories.cash_register.unit_of_work import (
        CashRegisterUnitOfWork,
    )
    from backend.infrastructure.sync.http_transport import HttpReplicationTransport

    _, _, emitida = central
    app = create_central_app(CentralSyncWorkflow(esquema, PostgresCentralInboxRepository))
    cliente = TestClient(app, base_url="http://testserver")
    db = sqlite3.connect(":memory:")
    importlib.import_module(
        "migrations.standalone.175_cash_register_bounded_context_schema").run(db)
    importlib.import_module("migrations.standalone.350_replication_engine").run(db)
    ReplicationOutboxService.register_station(db, station_id=emitida.station_id,
                                              branch_id=emitida.branch_id)
    evento = cash_event_payload(CashEvents.HARDWARE_DIAGNOSED, operation_id=new_uuid(),
                                entity_id=new_uuid(), branch_id=emitida.branch_id,
                                user_id=new_uuid(), amount="1250.50")
    with CashRegisterUnitOfWork(db) as uow:
        uow.events.add(evento)
        uow.outbox.enqueue(evento)
    motor = ReplicationOutboxService(HttpReplicationTransport(
        "http://testserver", station_id=emitida.station_id, secret=emitida.secret,
        client=cliente, allow_insecure_localhost=True), rng=random.Random(1))
    assert motor.synchronize(db, station_id=emitida.station_id, now=T0).synced == 1
    conn = esquema()
    fila = _uno(conn, "SELECT status, payload->>'amount', occurred_at FROM sync_inbox"
                      " WHERE event_id=%s", (evento["event_id"],))
    conn.close()
    assert fila[0] == "APPLIED" and fila[1] == "1250.50" and fila[2].tzinfo is not None
    db.close()
    assert json.loads(json.dumps({"ok": True}))
