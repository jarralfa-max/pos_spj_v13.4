"""Reglas de la ingesta central (Slice 4) con el libro EN MEMORIA.

La misma batería corre contra PostgreSQL real en
`tests/integration/central_pg/test_central_ingestion_pg.py` (CI).
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from decimal import Decimal

import pytest

from backend.application.sync.central_ingestion import (
    MAX_BATCH,
    CentralIngestionService,
    StationAuthenticationError,
    StationNotAllowedError,
)
from backend.application.sync.station_admin import CentralStationAdmin
from backend.application.sync.station_credentials import (
    issue_station_secret,
    station_secret_hash,
    verify_station_secret,
)
from backend.shared.ids import new_uuid
from backend.shared.sync.replication_envelope import ReplicationEnvelope, ReplicationOutcome
from tests.unit.central_sync.memory_inbox import MemoryCentralInbox

T0 = datetime(2026, 10, 25, 12, 0, tzinfo=timezone.utc)


@pytest.fixture
def central():
    repo = MemoryCentralInbox()
    emitida = CentralStationAdmin(repo).register(station_id=new_uuid(), branch_id=new_uuid(),
                                                 display_name="Caja 1")
    return repo, emitida


def sobre(estacion, sucursal, *, secuencia=1, agregado=None, version=1, **cambios):
    datos = dict(event_id=new_uuid(), operation_id=new_uuid(), event_type="SALE_COMPLETED",
                 schema_version=1, aggregate_type="sales.sale",
                 aggregate_id=agregado or new_uuid(), aggregate_version=version,
                 branch_id=sucursal, workstation_id=estacion, sequence_no=secuencia,
                 occurred_at=T0, actor_id=new_uuid(), payload={"total": Decimal("100.00")})
    datos.update(cambios)
    return ReplicationEnvelope(**datos)


def _ingesta(repo, emitida, *sobres):
    servicio = CentralIngestionService(repo)
    estacion = servicio.authenticate(emitida.station_id, emitida.secret)
    return [a for a in servicio.ingest(estacion, [s.to_dict() if hasattr(s, "to_dict") else s
                                                  for s in sobres], now=T0).acks]


# ── credenciales ─────────────────────────────────────────────────────────────
def test_station_secret_is_random_long_and_only_its_hash_is_stored(central):
    repo, emitida = central
    a, _ = issue_station_secret()
    b, _ = issue_station_secret()
    assert a != b and len(a) > 40 and a.startswith("spjst_")
    guardada = repo.stations[emitida.station_id]["credential_hash"]
    assert guardada == station_secret_hash(emitida.secret) and emitida.secret not in str(repo.stations)
    assert verify_station_secret(emitida.secret, guardada)
    assert not verify_station_secret("otro", guardada) and not verify_station_secret(None, guardada)


def test_authentication_never_says_which_part_failed(central):
    repo, emitida = central
    servicio = CentralIngestionService(repo)
    for station, secret in ((emitida.station_id, "malo"), (new_uuid(), emitida.secret),
                            ("1", emitida.secret), (None, None)):
        with pytest.raises(StationAuthenticationError, match="inválida"):
            servicio.authenticate(station, secret)


def test_suspended_and_retired_stations_cannot_send(central):
    repo, emitida = central
    admin = CentralStationAdmin(repo)
    admin.suspend(emitida.station_id)
    with pytest.raises(StationNotAllowedError):
        CentralIngestionService(repo).authenticate(emitida.station_id, emitida.secret)
    admin.reactivate(emitida.station_id)
    CentralIngestionService(repo).authenticate(emitida.station_id, emitida.secret)
    admin.retire(emitida.station_id)
    with pytest.raises(StationNotAllowedError):
        CentralIngestionService(repo).authenticate(emitida.station_id, emitida.secret)
    with pytest.raises(ValueError, match="no se reactiva"):
        admin.reactivate(emitida.station_id)


# ── resultados por sobre ─────────────────────────────────────────────────────
def test_accepts_new_facts_and_advances_the_station(central):
    repo, emitida = central
    antes = repo.commits
    acuses = _ingesta(repo, emitida, sobre(emitida.station_id, emitida.branch_id, secuencia=1),
                      sobre(emitida.station_id, emitida.branch_id, secuencia=2))
    assert [a.outcome for a in acuses] == [ReplicationOutcome.ACCEPTED] * 2
    assert repo.stations[emitida.station_id]["last_sequence"] == 2
    hecho = next(iter(repo.facts.values()))
    assert hecho["payload"] == {"total": "100.00"}
    assert repo.commits == antes + 1   # un lote = una confirmación


def test_a_resent_fact_is_a_duplicate_and_settles(central):
    repo, emitida = central
    s = sobre(emitida.station_id, emitida.branch_id)
    _ingesta(repo, emitida, s)
    otra_vez = _ingesta(repo, emitida, s)
    assert otra_vez[0].outcome is ReplicationOutcome.DUPLICATE and otra_vez[0].outcome.settles
    assert len(repo.facts) == 1


def test_same_event_id_with_other_content_is_a_conflict_never_an_overwrite(central):
    repo, emitida = central
    original = sobre(emitida.station_id, emitida.branch_id)
    _ingesta(repo, emitida, original)
    alterado = sobre(emitida.station_id, emitida.branch_id, secuencia=2,
                     event_id=original.event_id, operation_id=original.operation_id,
                     payload={"total": Decimal("1.00")})
    acuse = _ingesta(repo, emitida, alterado)[0]
    assert (acuse.outcome, acuse.error_code) == (ReplicationOutcome.CONFLICT, "EVENT_ID_REUSED")
    assert repo.facts[original.event_id]["payload"] == {"total": "100.00"}
    assert repo.conflicts[0]["kind"] == "EVENT_ID_REUSED"


def test_a_reused_station_sequence_is_a_conflict(central):
    """Una base de estación restaurada de un respaldo viejo vuelve a numerar."""
    repo, emitida = central
    _ingesta(repo, emitida, sobre(emitida.station_id, emitida.branch_id, secuencia=5))
    acuse = _ingesta(repo, emitida, sobre(emitida.station_id, emitida.branch_id, secuencia=5))[0]
    assert (acuse.outcome, acuse.error_code) == (ReplicationOutcome.CONFLICT, "SEQUENCE_REUSED")


def test_an_aggregate_version_regression_from_the_same_station_is_recorded(central):
    repo, emitida = central
    agregado = new_uuid()
    _ingesta(repo, emitida, sobre(emitida.station_id, emitida.branch_id, secuencia=1,
                                  agregado=agregado, version=2))
    acuse = _ingesta(repo, emitida, sobre(emitida.station_id, emitida.branch_id, secuencia=2,
                                          agregado=agregado, version=1))[0]
    assert acuse.error_code == "AGGREGATE_VERSION_REGRESSION"
    estados = sorted(f["status"] for f in repo.facts.values())
    assert estados == ["APPLIED", "CONFLICT"] and repo.conflicts[-1]["kind"] == acuse.error_code


def test_independent_versions_from_another_station_are_not_a_conflict(central):
    repo, emitida = central
    otra = CentralStationAdmin(repo).register(station_id=new_uuid(), branch_id=emitida.branch_id)
    agregado = new_uuid()
    _ingesta(repo, emitida, sobre(emitida.station_id, emitida.branch_id, agregado=agregado,
                                  version=5))
    acuse = _ingesta(repo, otra, sobre(otra.station_id, otra.branch_id, agregado=agregado,
                                       version=1))[0]
    assert acuse.outcome is ReplicationOutcome.ACCEPTED


# ── alcance y contrato ───────────────────────────────────────────────────────
def test_a_station_cannot_write_another_branch_or_impersonate_a_station(central):
    repo, emitida = central
    ajena = _ingesta(repo, emitida, sobre(emitida.station_id, new_uuid()))[0]
    suplantada = _ingesta(repo, emitida, sobre(new_uuid(), emitida.branch_id))[0]
    assert (ajena.outcome, ajena.error_code) == (ReplicationOutcome.REJECTED, "BRANCH_SCOPE")
    assert suplantada.error_code == "STATION_MISMATCH"
    assert repo.facts == {}


def test_tampered_or_malformed_envelopes_are_rejected_with_a_code(central):
    repo, emitida = central
    alterado = json.loads(sobre(emitida.station_id, emitida.branch_id).to_json())
    alterado["payload"]["total"] = "0.01"
    acuses = _ingesta(repo, emitida, alterado, {"event_id": "x"}, "no es un objeto")
    assert [a.error_code for a in acuses] == ["CONTENT_HASH_MISMATCH", "ENVELOPE_VERSION_UNSUPPORTED",
                                              "MALFORMED"]
    assert all(a.outcome is ReplicationOutcome.REJECTED for a in acuses)


def test_a_storage_error_retries_only_that_envelope(central):
    repo, emitida = central
    malo = sobre(emitida.station_id, emitida.branch_id, secuencia=1)
    bueno = sobre(emitida.station_id, emitida.branch_id, secuencia=2)
    repo.fail_on = malo.event_id
    acuses = _ingesta(repo, emitida, malo, bueno)
    assert [a.outcome for a in acuses] == [ReplicationOutcome.RETRY, ReplicationOutcome.ACCEPTED]
    assert list(repo.facts) == [bueno.event_id]
    assert repo.stations[emitida.station_id]["last_sequence"] == 0   # hueco en la 1


def test_batch_size_is_capped(central):
    repo, emitida = central
    servicio = CentralIngestionService(repo)
    estacion = servicio.authenticate(emitida.station_id, emitida.secret)
    with pytest.raises(ValueError):
        servicio.ingest(estacion, [{}] * (MAX_BATCH + 1))


def test_a_concurrent_winner_turns_the_loser_into_a_duplicate(central):
    """La base garantiza un solo insert (PK); quien pierde la carrera responde
    según la huella guardada, nunca ACCEPTED dos veces."""
    repo, emitida = central
    s = sobre(emitida.station_id, emitida.branch_id)
    original = repo.insert_fact

    def otro_gana_primero(envelope, **kw):
        original(envelope, **kw)          # la entrega concurrente inserta…
        return False                      # …y la nuestra no inserta nada

    repo.insert_fact = otro_gana_primero
    acuse = _ingesta(repo, emitida, s)[0]
    assert acuse.outcome is ReplicationOutcome.DUPLICATE
