"""Un hecho en CONFLICTO no se pierde al reenviarlo (SDLC-SYNC-002).

Estación: SQLite con el outbox REAL de Caja y el motor de replicación. Central:
`CentralIngestionService` sobre el libro EN MEMORIA; el mismo recorrido contra
PostgreSQL real está en `test_central_ingestion_pg.py` (CI).

La resolución la hace la ESTACIÓN, en Configuración → Offline (decisión del
responsable, 2026-11-05).
"""

from __future__ import annotations

import importlib
import random
import sqlite3
from datetime import datetime, timedelta, timezone

import pytest

from backend.application.configuracion.authorization import (
    ConfiguracionAuthorizationPolicy,
    DenyAllConfiguracionPermissionCheckerForTests,
)
from backend.application.sync.central_ingestion import CentralIngestionService
from backend.application.sync.replication_conflicts import (
    ACCEPT_REMOTE,
    RETRY_LOCAL,
    ReplicationConflictQuery,
    ResolveReplicationConflictUseCase,
)
from backend.application.sync.replication_outbox import ReplicationOutboxService
from backend.application.sync.station_admin import CentralStationAdmin
from backend.domain.cash_register.events import CashEvents, cash_event_payload
from backend.domain.settings.exceptions import ConfigurationPermissionDeniedError
from backend.infrastructure.db.repositories.cash_register.unit_of_work import (
    CashRegisterUnitOfWork,
)
from backend.infrastructure.db.repositories.replication.conflict_unit_of_work import (
    ReplicationConflictUnitOfWork,
)
from backend.shared.ids import new_uuid
from tests.unit.central_sync.memory_inbox import MemoryCentralInbox

T0 = datetime(2026, 10, 25, 12, 0, tzinfo=timezone.utc)
ACTOR = new_uuid()


class _Transporte:
    """La red: entrega los sobres a la ingesta central real."""

    def __init__(self, repositorio, emitida):
        self._servicio = CentralIngestionService(repositorio)
        self._emitida = emitida

    def push(self, *, station_id, branch_id, envelopes):
        estacion = self._servicio.authenticate(self._emitida.station_id, self._emitida.secret)
        return list(self._servicio.ingest(estacion, [s.to_dict() for s in envelopes],
                                          now=T0).acks)


@pytest.fixture
def central():
    repositorio = MemoryCentralInbox()
    return repositorio, CentralStationAdmin(repositorio).register(
        station_id=new_uuid(), branch_id=new_uuid(), display_name="Caja 1")


@pytest.fixture
def db(central):
    _, emitida = central
    c = sqlite3.connect(":memory:")
    importlib.import_module(
        "migrations.standalone.175_cash_register_bounded_context_schema").run(c)
    importlib.import_module("migrations.standalone.350_replication_engine").run(c)
    c.execute("""CREATE TABLE audit_logs (id TEXT PRIMARY KEY, accion TEXT, modulo TEXT,
                 entidad TEXT, entidad_id TEXT, usuario TEXT, sucursal_id TEXT, valor_antes TEXT,
                 valor_despues TEXT, detalles TEXT, fecha TEXT DEFAULT (datetime('now')))""")
    ReplicationOutboxService.register_station(c, station_id=emitida.station_id,
                                              branch_id=emitida.branch_id, now=T0)
    c.commit()
    yield c
    c.close()


def _hecho_en_conflicto(db, central):
    """Un hecho de caja cuya versión de agregado ya está superada en el central."""
    repositorio, emitida = central
    evento = cash_event_payload(CashEvents.HARDWARE_DIAGNOSED, operation_id=new_uuid(),
                                entity_id=new_uuid(), branch_id=emitida.branch_id,
                                user_id=new_uuid())
    with CashRegisterUnitOfWork(db) as uow:
        uow.events.add(evento)
        uow.outbox.enqueue(evento)
    motor = ReplicationOutboxService(_Transporte(repositorio, emitida), rng=random.Random(7))
    assert motor.stage(db, station_id=emitida.station_id, now=T0) == 1
    agregado = db.execute("SELECT aggregate_type, aggregate_id FROM replication_envelopes"
                          ).fetchone()
    repositorio.facts[new_uuid()] = {
        "station_id": emitida.station_id, "sequence_no": 900, "content_hash": "b" * 64,
        "status": "APPLIED", "error_code": None, "aggregate": tuple(agregado),
        "aggregate_version": 7, "payload": {}}
    motor.synchronize(db, station_id=emitida.station_id, now=T0)
    return motor, evento


def _estado(db) -> str:
    return db.execute("SELECT state FROM replication_envelopes").fetchone()[0]


def _resolver(db, *, autorizacion=None):
    return ResolveReplicationConflictUseCase(
        lambda: ReplicationConflictUnitOfWork(db),
        autorizacion or ConfiguracionAuthorizationPolicy.permissive_for_tests())


def _sobre_id(db) -> str:
    return db.execute("SELECT id FROM replication_envelopes").fetchone()[0]


def test_a_requeued_conflict_stays_in_conflict_and_never_becomes_synced(db, central):
    motor, evento = _hecho_en_conflicto(db, central)
    repositorio, emitida = central
    assert _estado(db) == "CONFLICT"

    _resolver(db).execute(envelope_id=_sobre_id(db), strategy=RETRY_LOCAL, reason="reintento",
                          actor=ACTOR, operation_id=new_uuid(), now=T0.isoformat())
    assert _estado(db) == "RETRY"
    motor.synchronize(db, station_id=emitida.station_id, now=T0 + timedelta(minutes=5))

    assert _estado(db) == "CONFLICT"
    assert repositorio.facts[evento["event_id"]]["status"] == "CONFLICT"


def test_a_lost_ack_does_not_turn_a_conflict_into_a_delivered_fact(db, central):
    """Sin ninguna acción humana: el central guardó el conflicto, el acuse se
    perdió y la estación reintenta sola."""
    motor, _ = _hecho_en_conflicto(db, central)
    _, emitida = central
    db.execute("UPDATE replication_envelopes SET state='RETRY', next_attempt_at=?",
               (T0.isoformat(),))
    db.commit()
    motor.synchronize(db, station_id=emitida.station_id, now=T0 + timedelta(minutes=5))
    assert _estado(db) == "CONFLICT"


def test_pending_conflicts_are_listed_for_the_person_in_charge(db, central):
    _hecho_en_conflicto(db, central)
    filas = ReplicationConflictQuery(db).pending()
    assert len(filas) == 1
    assert filas[0].source == "cash_register"
    assert filas[0].error.startswith("AGGREGATE_VERSION_REGRESSION")


def test_no_replication_engine_means_no_conflicts():
    c = sqlite3.connect(":memory:")
    assert ReplicationConflictQuery(c).pending() == ()
    c.close()


def test_accepting_the_server_version_is_explicit_and_audited(db, central):
    _hecho_en_conflicto(db, central)
    operacion = new_uuid()
    envelope_id = _sobre_id(db)
    _resolver(db).execute(envelope_id=envelope_id, strategy=ACCEPT_REMOTE,
                          reason="El central ya tiene la versión buena", actor=ACTOR,
                          operation_id=operacion)
    assert _estado(db) == "SYNCED"
    assert ReplicationConflictQuery(db).pending() == ()
    usuario, entidad, detalles = db.execute(
        "SELECT usuario, entidad_id, detalles FROM audit_logs"
        " WHERE accion='sincronizacion.conflicto.resolver'").fetchone()
    assert (usuario, entidad) == (ACTOR, envelope_id)
    assert ACCEPT_REMOTE in detalles and operacion in detalles
    assert "El central ya tiene la versión buena" in detalles


def test_resolution_requires_a_reason(db, central):
    _hecho_en_conflicto(db, central)
    with pytest.raises(ValueError):
        _resolver(db).execute(envelope_id=_sobre_id(db), strategy=ACCEPT_REMOTE, reason="  ",
                              actor=ACTOR, operation_id=new_uuid())
    assert _estado(db) == "CONFLICT"


def test_resolution_is_denied_without_the_permission(db, central):
    _hecho_en_conflicto(db, central)
    negado = ConfiguracionAuthorizationPolicy(DenyAllConfiguracionPermissionCheckerForTests())
    with pytest.raises(ConfigurationPermissionDeniedError):
        _resolver(db, autorizacion=negado).execute(
            envelope_id=_sobre_id(db), strategy=ACCEPT_REMOTE, reason="motivo", actor=ACTOR,
            operation_id=new_uuid())
    assert _estado(db) == "CONFLICT"


def test_a_conflict_cannot_be_resolved_twice(db, central):
    _hecho_en_conflicto(db, central)
    envelope_id = _sobre_id(db)
    _resolver(db).execute(envelope_id=envelope_id, strategy=ACCEPT_REMOTE, reason="uno",
                          actor=ACTOR, operation_id=new_uuid())
    with pytest.raises(LookupError):
        _resolver(db).execute(envelope_id=envelope_id, strategy=RETRY_LOCAL, reason="dos",
                              actor=ACTOR, operation_id=new_uuid())
    assert _estado(db) == "SYNCED"
    assert db.execute("SELECT count(*) FROM audit_logs").fetchone()[0] == 1
