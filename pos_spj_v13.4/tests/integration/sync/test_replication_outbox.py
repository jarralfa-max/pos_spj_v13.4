"""Motor de replicación único (arquitectura híbrida, Slice 2), con outbox REALES
de Caja e Inventario y la migración 350 sobre su esquema."""

from __future__ import annotations

import importlib
import json
import random
import sqlite3
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from backend.application.sync.replication_outbox import (
    LEASE,
    MAX_ATTEMPTS,
    ReplicationOutboxService,
    RetryPolicy,
)
from backend.domain.cash_register.events import CashEvents, cash_event_payload
from backend.infrastructure.db.repositories.cash_register.unit_of_work import (
    CashRegisterUnitOfWork,
)
from backend.infrastructure.db.repositories.replication.unit_of_work import (
    ReplicationUnitOfWork,
)
from backend.infrastructure.db.schema.inventory_schema import create_inventory_schema
from backend.shared.ids import new_uuid
from backend.shared.sync.replication_envelope import ReplicationAck, ReplicationEnvelope

T0 = datetime(2026, 10, 24, 12, 0, tzinfo=timezone.utc)
_350 = importlib.import_module("migrations.standalone.350_replication_engine")


class Servidor:
    """Transporte de prueba: responde por event_id lo que se le indique."""

    def __init__(self, default="ACCEPTED", **por_evento):
        self.default, self.por_evento, self.lotes = default, por_evento, []
        self.omitir: set[str] = set()

    def push(self, *, station_id, branch_id, envelopes):
        self.lotes.append(list(envelopes))
        acuses = []
        for sobre in envelopes:
            if sobre.event_id in self.omitir:
                continue
            resultado = self.por_evento.get(sobre.event_id, self.default)
            acuses.append(ReplicationAck(
                sobre.event_id, resultado, remote_revision="r1",
                error_code="" if resultado in ("ACCEPTED", "DUPLICATE") else f"E_{resultado}"))
        return acuses


class Caido:
    def __init__(self):
        self.llamadas = 0

    def push(self, **_):
        self.llamadas += 1
        raise ConnectionError("sin red")


@pytest.fixture
def db():
    c = sqlite3.connect(":memory:")
    importlib.import_module(
        "migrations.standalone.175_cash_register_bounded_context_schema").run(c)
    create_inventory_schema(c)
    _350.run(c)
    c.commit()
    yield c
    c.close()


@pytest.fixture
def estacion(db):
    sucursal, est = new_uuid(), new_uuid()
    ReplicationOutboxService.register_station(db, station_id=est, branch_id=sucursal, now=T0)
    return est, sucursal


def _caja(db, sucursal, *, entidad=None, **extra):
    evento = cash_event_payload(CashEvents.HARDWARE_DIAGNOSED, operation_id=new_uuid(),
                                entity_id=entidad or new_uuid(), branch_id=sucursal,
                                user_id=new_uuid(), **extra)
    with CashRegisterUnitOfWork(db) as uow:
        uow.events.add(evento)
        uow.outbox.enqueue(evento)
    return evento


def _inventario(db, sucursal, payload=None):
    evento = {"event_id": new_uuid(), "event_name": "INVENTORY_MOVEMENT_POSTED",
              "operation_id": new_uuid(), "entity_id": new_uuid(), "branch_id": sucursal,
              "user_id": new_uuid(), "timestamp": T0.isoformat(),
              "payload": payload if payload is not None else {"qty": "2.500"}}
    db.execute("INSERT INTO inventory_outbox (id, event_id, event_name, payload_json,"
               " operation_id, status, created_at) VALUES (?,?,?,?,?,'PENDING',?)",
               (new_uuid(), evento["event_id"], evento["event_name"],
                json.dumps(evento) if not isinstance(payload, str) else payload,
                evento["operation_id"], T0.isoformat()))
    db.commit()
    return evento


def _motor(transporte, **kw):
    return ReplicationOutboxService(transporte, rng=random.Random(7), **kw)


def _estados(db):
    return dict(db.execute(
        "SELECT event_id, state FROM replication_envelopes").fetchall())


# ── preparar ─────────────────────────────────────────────────────────────────
def test_stages_every_context_in_order_with_station_sequence(db, estacion):
    est, suc = estacion
    a = _caja(db, suc)
    b = _inventario(db, suc)
    entidad = new_uuid()
    c1 = _caja(db, suc, entidad=entidad)
    c2 = _caja(db, suc, entidad=entidad)
    assert _motor(Servidor()).stage(db, station_id=est, now=T0) == 4
    filas = db.execute("SELECT event_id, source, sequence_no, aggregate_type, aggregate_version"
                       " FROM replication_envelopes ORDER BY sequence_no").fetchall()
    assert [f[2] for f in filas] == [1, 2, 3, 4]
    por_evento = {f[0]: f for f in filas}
    assert por_evento[b["event_id"]][1:4:2] == ("inventory", "inventory.stock")
    assert por_evento[a["event_id"]][3] == "cash_register.cash"
    assert (por_evento[c1["event_id"]][4], por_evento[c2["event_id"]][4]) == (1, 2)
    # Preparar otra vez no duplica nada.
    assert _motor(Servidor()).stage(db, station_id=est, now=T0) == 0


def test_staged_envelope_is_the_canonical_contract(db, estacion):
    est, suc = estacion
    evento = _caja(db, suc)
    _motor(Servidor()).stage(db, station_id=est, now=T0)
    texto = db.execute("SELECT envelope_json FROM replication_envelopes").fetchone()[0]
    sobre = ReplicationEnvelope.from_json(texto)
    assert (sobre.event_id, sobre.branch_id, sobre.workstation_id, sobre.event_type) == (
        evento["event_id"], suc, est, CashEvents.HARDWARE_DIAGNOSED)


# ── la regla que el motor viejo rompía ───────────────────────────────────────
def test_never_touches_the_context_outbox_status(db, estacion):
    """El despachador Caja → Finanzas sólo toma filas PENDING de cash_outbox."""
    est, suc = estacion
    _caja(db, suc)
    _motor(Caido()).synchronize(db, station_id=est, now=T0)
    _motor(Servidor()).synchronize(db, station_id=est, now=T0 + timedelta(hours=1))
    assert db.execute("SELECT DISTINCT status FROM cash_outbox").fetchall() == [("PENDING",)]


# ── acuses ───────────────────────────────────────────────────────────────────
def test_accepted_and_duplicate_settle_and_advance_the_station(db, estacion):
    est, suc = estacion
    a, b = _caja(db, suc), _caja(db, suc)
    resultado = _motor(Servidor(**{b["event_id"]: "DUPLICATE"})).synchronize(
        db, station_id=est, now=T0)
    assert (resultado.status, resultado.sent, resultado.synced) == ("IDLE", 2, 2)
    assert set(_estados(db).values()) == {"SYNCED"}
    fila = db.execute("SELECT last_synced_sequence, sync_status FROM replication_stations"
                      " WHERE id=?", (est,)).fetchone()
    assert fila == (2, "IDLE")


def test_transport_down_keeps_everything_queued_with_jittered_backoff(db, estacion):
    est, suc = estacion
    _caja(db, suc)
    caido = Caido()
    resultado = _motor(caido).synchronize(db, station_id=est, now=T0)
    assert (resultado.status, resultado.retries) == ("RETRYING", 1)
    estado, intento, siguiente, error = db.execute(
        "SELECT state, attempt_count, next_attempt_at, last_error FROM replication_envelopes"
    ).fetchone()
    assert (estado, intento) == ("RETRY", 1) and error.startswith("TRANSPORT_UNAVAILABLE")
    assert T0 < datetime.fromisoformat(siguiente) <= T0 + timedelta(seconds=4)
    # Antes de su hora no se reintenta.
    _motor(caido).synchronize(db, station_id=est, now=T0)
    assert caido.llamadas == 1


def test_retry_policy_is_bounded_and_spread():
    politica, rng = RetryPolicy(), random.Random(1)
    esperas = [politica.delay(n, rng).total_seconds() for n in range(30)]
    assert all(1 <= s <= 15 * 60 for s in esperas)
    assert len({round(s) for s in esperas[10:]}) > 5   # con jitter, no todas iguales


def test_conflict_blocks_only_its_own_aggregate(db, estacion):
    est, suc = estacion
    entidad = new_uuid()
    primero = _caja(db, suc, entidad=entidad)
    _motor(Servidor(**{primero["event_id"]: "CONFLICT"})).synchronize(db, station_id=est, now=T0)
    segundo_mismo = _caja(db, suc, entidad=entidad)
    otro = _caja(db, suc)
    servidor = Servidor()
    resultado = _motor(servidor).synchronize(db, station_id=est, now=T0)
    enviados = {s.event_id for s in servidor.lotes[0]}
    assert otro["event_id"] in enviados and segundo_mismo["event_id"] not in enviados
    assert resultado.status == "CONFLICT"
    assert _estados(db)[primero["event_id"]] == "CONFLICT"


def test_rejected_goes_to_dead_letter_and_missing_ack_retries(db, estacion):
    est, suc = estacion
    rechazado, sin_acuse = _caja(db, suc), _caja(db, suc)
    servidor = Servidor(**{rechazado["event_id"]: "REJECTED"})
    servidor.omitir.add(sin_acuse["event_id"])
    resultado = _motor(servidor).synchronize(db, station_id=est, now=T0)
    estados = _estados(db)
    assert estados[rechazado["event_id"]] == "DEAD"
    assert estados[sin_acuse["event_id"]] == "RETRY"
    assert db.execute("SELECT last_error FROM replication_envelopes WHERE event_id=?",
                      (sin_acuse["event_id"],)).fetchone()[0] == "NO_ACK"
    assert resultado.dead == 1


def test_too_many_attempts_become_dead_and_can_be_requeued(db, estacion):
    est, suc = estacion
    _caja(db, suc)
    _motor(Servidor()).stage(db, station_id=est, now=T0)
    db.execute("UPDATE replication_envelopes SET attempt_count=?", (MAX_ATTEMPTS,))
    db.commit()
    _motor(Caido()).synchronize(db, station_id=est, now=T0)
    estado, error, sobre_id = db.execute(
        "SELECT state, last_error, id FROM replication_envelopes").fetchone()
    assert estado == "DEAD" and error.startswith("MAX_ATTEMPTS")
    with ReplicationUnitOfWork(db) as uow:
        assert uow.replication.requeue(envelope_id=sobre_id, now=T0.isoformat())
    assert db.execute("SELECT state, attempt_count FROM replication_envelopes").fetchone() == (
        "RETRY", 0)


# ── recuperación y casos raros ───────────────────────────────────────────────
def test_interrupted_in_flight_envelopes_are_recovered_after_the_lease(db, estacion):
    est, suc = estacion
    _caja(db, suc)
    motor = _motor(Servidor())
    motor.stage(db, station_id=est, now=T0)
    with ReplicationUnitOfWork(db) as uow:   # simula un cierre a media entrega
        uow.replication.claim_ready(station_id=est, now=T0.isoformat(timespec="seconds"),
                                    limit=10)
    pronto = motor.synchronize(db, station_id=est, now=T0 + LEASE - timedelta(seconds=30))
    assert pronto.recovered == 0
    tarde = motor.synchronize(db, station_id=est, now=T0 + LEASE + timedelta(seconds=1))
    assert tarde.recovered == 1 and tarde.synced == 1


def test_an_invalid_fact_is_dead_and_visible_without_blocking_the_rest(db, estacion):
    est, suc = estacion
    malo = _inventario(db, suc, payload='{"event_id":"x","timestamp":"2026-10-24T12:00:00+00:00",'
                                        '"payload":{"qty":2.5}}')
    bueno = _caja(db, suc)
    resultado = _motor(Servidor()).synchronize(db, station_id=est, now=T0)
    assert resultado.synced == 1 and resultado.dead == 1
    error = db.execute("SELECT last_error FROM replication_envelopes WHERE source='inventory'"
                       ).fetchone()[0]
    assert error.startswith("FLOAT_NOT_ALLOWED")
    assert _estados(db)[bueno["event_id"]] == "SYNCED"
    assert malo["event_id"] not in _estados(db)   # su id derivado, no el inválido


def test_the_same_fact_in_two_outboxes_is_sent_once(db, estacion):
    est, suc = estacion
    evento = _caja(db, suc)
    db.execute("INSERT INTO inventory_outbox (id, event_id, event_name, payload_json,"
               " operation_id, status, created_at) VALUES (?,?,?,?,?,'PENDING',?)",
               (new_uuid(), evento["event_id"], evento["event_name"], json.dumps(evento),
                evento["operation_id"], T0.isoformat()))
    db.commit()
    servidor = Servidor()
    _motor(servidor).synchronize(db, station_id=est, now=T0)
    assert [s.event_id for s in servidor.lotes[0]] == [evento["event_id"]]
    assert db.execute("SELECT last_error FROM replication_envelopes WHERE state='DEAD'"
                      ).fetchone()[0].startswith("DUPLICATE_EVENT_ID_ACROSS_SOURCES")


def test_offline_station_never_calls_the_transport(db, estacion):
    est, suc = estacion
    _caja(db, suc)
    with ReplicationUnitOfWork(db) as uow:
        uow.replication.set_connectivity(station_id=est, online=False, now=T0.isoformat())
    caido = Caido()
    assert _motor(caido).synchronize(db, station_id=est, now=T0).status == "OFFLINE"
    assert caido.llamadas == 0


def test_money_travels_exact_from_outbox_to_wire(db, estacion):
    est, suc = estacion
    _caja(db, suc, amount=str(Decimal("1250.50")))
    servidor = Servidor()
    _motor(servidor).synchronize(db, station_id=est, now=T0)
    assert servidor.lotes[0][0].payload["amount"] == "1250.50"


# ── migración 350 ────────────────────────────────────────────────────────────
def test_migration_350_moves_devices_and_returns_damaged_rows_to_finance():
    c = sqlite3.connect(":memory:")
    importlib.import_module(
        "migrations.standalone.175_cash_register_bounded_context_schema").run(c)
    dispositivo, sucursal = new_uuid(), new_uuid()
    c.execute("INSERT INTO cash_sync_devices (id, branch_id, local_sequence,"
              " last_synced_sequence, connectivity, sync_status, updated_at)"
              " VALUES (?,?,3,0,'OFFLINE','RETRYING',?)", (dispositivo, sucursal, T0.isoformat()))
    filas = {"nunca": (None, "TRANSPORT_UNAVAILABLE"), "ya_asentada": (T0.isoformat(),
             "SYNC_CONFLICT"), "otro_error": (None, "FINANCE_DOWN")}
    ids = {}
    for clave, (despachada, error) in filas.items():
        # Hecho real de Caja, después dañado como lo dejaba el motor de CASH-19.
        ids[clave] = _caja(c, sucursal)["event_id"]
        c.execute("UPDATE cash_outbox SET status='FAILED', dispatched_at=?, last_error=?"
                  " WHERE event_id=?", (despachada, error, ids[clave]))
    c.commit()
    _350.run(c)
    _350.run(c)
    por_id = dict(c.execute("SELECT event_id, status FROM cash_outbox").fetchall())
    estado = {clave: por_id[ids[clave]] for clave in filas}
    assert estado == {"nunca": "PENDING", "ya_asentada": "DISPATCHED", "otro_error": "FAILED"}
    assert c.execute("SELECT branch_id, connectivity FROM replication_stations WHERE id=?",
                     (dispositivo,)).fetchone() == (sucursal, "OFFLINE")
