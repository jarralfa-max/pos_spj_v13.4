"""De la caja al servidor central por la API real (Slice 4).

Estación: SQLite con el outbox REAL de Caja + motor de replicación (Slice 2) +
`HttpReplicationTransport`. Servidor: `create_central_app` (FastAPI) +
`CentralIngestionService`. El libro central es el de MEMORIA (simulación); el
mismo recorrido contra PostgreSQL real está en
`tests/integration/central_pg/test_central_ingestion_pg.py` (CI).
"""

from __future__ import annotations

import importlib
import json
import random
import sqlite3
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient

from backend.api.central_app import CentralSyncWorkflow, create_central_app
from backend.application.sync.replication_outbox import ReplicationOutboxService
from backend.application.sync.station_admin import CentralStationAdmin
from backend.domain.cash_register.events import CashEvents, cash_event_payload
from backend.infrastructure.db.repositories.cash_register.unit_of_work import (
    CashRegisterUnitOfWork,
)
from backend.infrastructure.sync.http_transport import HttpReplicationTransport
from backend.shared.ids import new_uuid
from tests.unit.central_sync.memory_inbox import MemoryCentralInbox

T0 = datetime(2026, 10, 25, 12, 0, tzinfo=timezone.utc)


class _Conexion:
    def close(self):
        pass

    def rollback(self):
        pass


@pytest.fixture
def servidor():
    libro = MemoryCentralInbox()
    app = create_central_app(CentralSyncWorkflow(lambda: _Conexion(), lambda _c: libro),
                             requests_per_minute=1000)
    return libro, TestClient(app, base_url="http://testserver")


@pytest.fixture
def caja(servidor):
    libro, cliente = servidor
    emitida = CentralStationAdmin(libro).register(station_id=new_uuid(), branch_id=new_uuid(),
                                                  display_name="Caja 1")
    db = sqlite3.connect(":memory:")
    importlib.import_module(
        "migrations.standalone.175_cash_register_bounded_context_schema").run(db)
    importlib.import_module("migrations.standalone.350_replication_engine").run(db)
    ReplicationOutboxService.register_station(db, station_id=emitida.station_id,
                                              branch_id=emitida.branch_id)
    transporte = HttpReplicationTransport(
        "http://testserver", station_id=emitida.station_id, secret=emitida.secret,
        client=cliente, allow_insecure_localhost=True)
    yield db, emitida, ReplicationOutboxService(transporte, rng=random.Random(3))
    db.close()


def _venta(db, emitida, **extra):
    evento = cash_event_payload(CashEvents.HARDWARE_DIAGNOSED, operation_id=new_uuid(),
                                entity_id=new_uuid(), branch_id=emitida.branch_id,
                                user_id=new_uuid(), **extra)
    with CashRegisterUnitOfWork(db) as uow:
        uow.events.add(evento)
        uow.outbox.enqueue(evento)
    return evento


def test_a_cash_fact_travels_from_the_till_to_the_central_ledger(servidor, caja):
    libro, _ = servidor
    db, emitida, motor = caja
    evento = _venta(db, emitida, amount="1250.50")
    resultado = motor.synchronize(db, station_id=emitida.station_id, now=T0)
    assert (resultado.status, resultado.synced) == ("IDLE", 1)
    hecho = libro.facts[evento["event_id"]]
    assert hecho["status"] == "APPLIED" and hecho["payload"]["amount"] == "1250.50"
    assert libro.stations[emitida.station_id]["last_sequence"] == 1
    assert db.execute("SELECT state FROM replication_envelopes").fetchone()[0] == "SYNCED"


def test_a_lost_response_after_the_server_commit_is_settled_as_duplicate(servidor, caja):
    """La respuesta se perdió tras confirmar en el servidor: la estación reenvía."""
    libro, _ = servidor
    db, emitida, motor = caja
    _venta(db, emitida)
    motor.synchronize(db, station_id=emitida.station_id, now=T0)
    db.execute("UPDATE replication_envelopes SET state='RETRY', next_attempt_at=NULL")
    db.commit()
    resultado = motor.synchronize(db, station_id=emitida.station_id, now=T0)
    assert resultado.synced == 1 and len(libro.facts) == 1


def test_a_till_with_a_wrong_secret_keeps_everything_queued(servidor, caja):
    libro, cliente = servidor
    db, emitida, _ = caja
    _venta(db, emitida)
    intruso = ReplicationOutboxService(HttpReplicationTransport(
        "http://testserver", station_id=emitida.station_id, secret="spjst_robado",
        client=cliente, allow_insecure_localhost=True))
    resultado = intruso.synchronize(db, station_id=emitida.station_id, now=T0)
    assert resultado.retries == 1 and libro.facts == {}
    assert "credencial" in db.execute("SELECT last_error FROM replication_envelopes").fetchone()[0]


# ── la API por sí misma ──────────────────────────────────────────────────────
def _post(cliente, emitida, sobres, **encabezados):
    base = {"X-SPJ-Station-Id": emitida.station_id, "Authorization": f"Bearer {emitida.secret}"}
    base.update(encabezados)
    return cliente.post("/api/v1/sync/events", json={"envelopes": sobres}, headers=base)


def test_api_auth_errors_are_generic_and_suspension_is_403(servidor, caja):
    libro, cliente = servidor
    _, emitida, _ = caja
    sin = cliente.post("/api/v1/sync/events", json={"envelopes": []})
    malo = _post(cliente, emitida, [], Authorization="Bearer x")
    assert sin.status_code == malo.status_code == 401
    assert sin.json() == malo.json()
    CentralStationAdmin(libro).suspend(emitida.station_id)
    assert _post(cliente, emitida, []).status_code == 403


def test_api_limits_and_request_id(servidor, caja):
    _, cliente = servidor
    _, emitida, _ = caja
    respuesta = _post(cliente, emitida, [], **{"X-Request-ID": "rastreo-1"})
    assert respuesta.status_code == 200 and respuesta.headers["X-Request-ID"] == "rastreo-1"
    assert _post(cliente, emitida, [{}] * 501).status_code == 413
    assert cliente.post("/api/v1/sync/events", content=b"{no json",
                        headers={"X-SPJ-Station-Id": emitida.station_id}).status_code == 400


def test_api_rate_limit_per_station():
    app = create_central_app(CentralSyncWorkflow(lambda: _Conexion(),
                                                 lambda _c: MemoryCentralInbox()),
                             requests_per_minute=2)
    cliente = TestClient(app)
    estacion = new_uuid()
    codigos = [cliente.post("/api/v1/sync/events", json={"envelopes": []},
                            headers={"X-SPJ-Station-Id": estacion}).status_code
               for _ in range(3)]
    assert codigos[-1] == 429


def test_unconfigured_server_says_so():
    cliente = TestClient(create_central_app(None))
    assert cliente.get("/health").json() == {"status": "unconfigured"}
    assert cliente.post("/api/v1/sync/events", json={"envelopes": []}).status_code == 503


def test_transport_refuses_plain_http_to_a_real_host():
    with pytest.raises(ValueError, match="HTTPS"):
        HttpReplicationTransport("http://central.spj.mx", station_id=new_uuid(), secret="s")
    with pytest.raises(ValueError, match="HTTPS"):
        HttpReplicationTransport("http://localhost:8100", station_id=new_uuid(), secret="s")
    HttpReplicationTransport("https://central.spj.mx", station_id=new_uuid(), secret="s")
    with pytest.raises(ValueError, match="credencial"):
        HttpReplicationTransport("https://central.spj.mx", station_id=new_uuid(), secret="")


def test_response_body_never_echoes_the_secret(servidor, caja):
    _, cliente = servidor
    _, emitida, _ = caja
    respuesta = _post(cliente, emitida, [])
    assert emitida.secret not in respuesta.text and emitida.secret not in json.dumps(
        dict(respuesta.headers))
