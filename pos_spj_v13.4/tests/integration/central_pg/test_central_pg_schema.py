"""Esquema central sobre un PostgreSQL REAL (arquitectura híbrida, Slice 3).

Corre sólo si existe `SPJ_TEST_PG_DSN` (el CI levanta un PostgreSQL 16 de
servicio: trabajo `central-postgres` de `.github/workflows/ci-segmented.yml`).
Cada prueba trabaja en un esquema propio que se borra al terminar.
"""

from __future__ import annotations

import json
import os
import uuid
from datetime import datetime, timedelta, timezone

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

T0 = datetime(2026, 10, 25, 12, 0, tzinfo=timezone.utc)


@pytest.fixture
def pg():
    conn = create_connection_factory(DatabaseSettings.postgresql(DSN))()
    esquema = f"t_{uuid.uuid4().hex[:12]}"
    with conn.cursor() as cur:
        cur.execute(f"CREATE SCHEMA {esquema}")
        cur.execute(f"SET search_path TO {esquema}")
    conn.commit()
    yield conn
    conn.rollback()
    with conn.cursor() as cur:
        cur.execute(f"DROP SCHEMA {esquema} CASCADE")
    conn.commit()
    conn.close()


def _uno(conn, sql, params=()):
    with conn.cursor() as cur:
        cur.execute(sql, params)
        return cur.fetchone()


def _estacion(conn):
    estacion = new_uuid()
    with conn.cursor() as cur:
        cur.execute("INSERT INTO sync_stations (id, branch_id, credential_hash)"
                    " VALUES (%s, %s, 'huella')", (estacion, new_uuid()))
    conn.commit()
    return estacion


def _hecho(conn, estacion, *, event_id=None, secuencia=1, status="APPLIED", error=None,
           payload=None):
    event_id = event_id or new_uuid()
    with conn.cursor() as cur:
        cur.execute(
            """INSERT INTO sync_inbox (event_id, station_id, sequence_no, content_hash,
               envelope_version, event_type, schema_version, aggregate_type, aggregate_id,
               aggregate_version, branch_id, operation_id, occurred_at, payload, status,
               error_code)
               VALUES (%s,%s,%s,%s,1,'SALE_COMPLETED',1,'sales.sale',%s,1,%s,%s,%s,%s,%s,%s)""",
            (event_id, estacion, secuencia, "a" * 64, new_uuid(), new_uuid(), new_uuid(), T0,
             json.dumps(payload or {"total": "1250.50"}), status, error))
    return event_id


def test_lane_is_idempotent_and_records_itself(pg):
    assert engine.up_postgresql(pg) == len(engine.PG_MIGRATIONS)
    assert engine.up_postgresql(pg) == 0
    assert _uno(pg, "SELECT count(*) FROM schema_migrations")[0] == len(engine.PG_MIGRATIONS)


def test_native_types_are_what_the_contract_says(pg):
    engine.up_postgresql(pg)
    with pg.cursor() as cur:
        cur.execute("""SELECT column_name, data_type FROM information_schema.columns
                       WHERE table_schema = current_schema() AND table_name = 'sync_inbox'""")
        tipos = dict(cur.fetchall())
    assert tipos["event_id"] == "uuid" and tipos["aggregate_id"] == "uuid"
    assert tipos["occurred_at"] == "timestamp with time zone"
    assert tipos["payload"] == "jsonb" and tipos["sequence_no"] == "bigint"
    assert not any(t in ("real", "double precision") for t in tipos.values())


def test_event_id_is_the_idempotency_key(pg):
    engine.up_postgresql(pg)
    estacion = _estacion(pg)
    evento = _hecho(pg, estacion)
    pg.commit()
    with pytest.raises(psycopg.errors.UniqueViolation):
        _hecho(pg, estacion, event_id=evento, secuencia=2)
    pg.rollback()
    with pg.cursor() as cur:   # la forma que usará la ingesta (Slice 4)
        cur.execute("""INSERT INTO sync_inbox (event_id, station_id, sequence_no, content_hash,
            envelope_version, event_type, schema_version, aggregate_type, aggregate_id,
            aggregate_version, branch_id, operation_id, occurred_at, payload, status)
            VALUES (%s,%s,3,%s,1,'X',1,'sales.sale',%s,1,%s,%s,%s,'{}','APPLIED')
            ON CONFLICT (event_id) DO NOTHING""",
                    (evento, estacion, "a" * 64, new_uuid(), new_uuid(), new_uuid(), T0))
        assert cur.rowcount == 0
    pg.commit()


def test_station_sequence_is_unique_and_station_must_exist(pg):
    engine.up_postgresql(pg)
    estacion = _estacion(pg)
    _hecho(pg, estacion, secuencia=1)
    pg.commit()
    with pytest.raises(psycopg.errors.UniqueViolation):
        _hecho(pg, estacion, secuencia=1)
    pg.rollback()
    with pytest.raises(psycopg.errors.ForeignKeyViolation):
        _hecho(pg, new_uuid())
    pg.rollback()


def test_a_non_applied_fact_must_say_why(pg):
    engine.up_postgresql(pg)
    estacion = _estacion(pg)
    with pytest.raises(psycopg.errors.CheckViolation):
        _hecho(pg, estacion, status="CONFLICT")
    pg.rollback()
    _hecho(pg, estacion, status="CONFLICT", error="EVENT_ID_REUSED")
    pg.commit()


def test_money_in_jsonb_and_instants_round_trip_exactly(pg):
    engine.up_postgresql(pg)
    estacion = _estacion(pg)
    evento = _hecho(pg, estacion, payload={"total": "1250.50", "qty": "1.250"})
    pg.commit()
    payload, instante = _uno(pg, "SELECT payload, occurred_at FROM sync_inbox WHERE event_id=%s",
                             (evento,))
    assert payload == {"total": "1250.50", "qty": "1.250"}
    assert instante == T0 and instante.utcoffset() == timedelta(0)


def test_retired_station_needs_a_retirement_date(pg):
    engine.up_postgresql(pg)
    with pytest.raises(psycopg.errors.CheckViolation):
        with pg.cursor() as cur:
            cur.execute("INSERT INTO sync_stations (id, branch_id, credential_hash, status)"
                        " VALUES (%s, %s, 'h', 'RETIRED')", (new_uuid(), new_uuid()))
    pg.rollback()


def test_a_second_process_does_not_get_the_migration_lock(pg):
    """Dos procesos no migran a la vez: mientras uno tiene el bloqueo, el otro no
    lo obtiene."""
    engine.up_postgresql(pg)
    otra = create_connection_factory(DatabaseSettings.postgresql(DSN))()
    try:
        with pg.cursor() as cur:
            cur.execute("SELECT pg_advisory_lock(%s)", (engine.PG_MIGRATION_LOCK_KEY,))
        with otra.cursor() as cur:
            cur.execute("SELECT pg_try_advisory_lock(%s)", (engine.PG_MIGRATION_LOCK_KEY,))
            assert cur.fetchone()[0] is False
    finally:
        with pg.cursor() as cur:
            cur.execute("SELECT pg_advisory_unlock(%s)", (engine.PG_MIGRATION_LOCK_KEY,))
        pg.commit()
        otra.close()
