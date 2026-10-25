"""Libro central de hechos en PostgreSQL (arquitectura híbrida, Slice 4).

Implementa `CentralInboxRepository`. SQL parametrizado (psycopg, `%s`); cada
sobre corre en un SAVEPOINT (`connection.transaction()` anidado), y el lote se
confirma al final. La unicidad la garantiza la base (`event_id` PK,
`UNIQUE (station_id, sequence_no)`): aunque dos solicitudes concurrentes traigan
el mismo hecho, sólo una lo inserta (`ON CONFLICT DO NOTHING`).
"""

from __future__ import annotations

import json
from contextlib import contextmanager
from datetime import datetime
from typing import Any, Mapping

from backend.shared.ids import new_uuid
from backend.shared.sync.replication_envelope import ReplicationEnvelope


class PostgresCentralInboxRepository:
    def __init__(self, connection: Any) -> None:
        self._conn = connection

    def _one(self, sql: str, params: tuple = ()):
        with self._conn.cursor() as cur:
            cur.execute(sql, params)
            return cur.fetchone()

    def _exec(self, sql: str, params: tuple = ()) -> int:
        with self._conn.cursor() as cur:
            cur.execute(sql, params)
            return cur.rowcount

    # ── estaciones ──────────────────────────────────────────────────────
    def get_station(self, station_id: str) -> Mapping[str, Any] | None:
        fila = self._one("SELECT id, branch_id, credential_hash, status, last_sequence"
                         " FROM sync_stations WHERE id = %s", (station_id,))
        if fila is None:
            return None
        return {"id": str(fila[0]), "branch_id": str(fila[1]), "credential_hash": fila[2],
                "status": fila[3], "last_sequence": int(fila[4])}

    def register_station(self, *, station_id: str, branch_id: str, display_name: str,
                         credential_hash: str) -> None:
        self._exec("INSERT INTO sync_stations (id, branch_id, display_name, credential_hash)"
                   " VALUES (%s, %s, %s, %s)",
                   (station_id, branch_id, display_name, credential_hash))

    def set_station_status(self, station_id: str, status: str, *, now: datetime) -> bool:
        return self._exec(
            "UPDATE sync_stations SET status = %s,"
            " retired_at = CASE WHEN %s = 'RETIRED' THEN %s ELSE retired_at END"
            " WHERE id = %s", (status, status, now, station_id)) == 1

    def touch_station(self, station_id: str, *, now: datetime) -> None:
        """Última secuencia CONTIGUA recibida, avanzando desde la conocida: un hueco
        (un sobre aún en conflicto en la estación) es donde la cuenta se detiene."""
        actual = int(self._one("SELECT last_sequence FROM sync_stations WHERE id = %s",
                               (station_id,))[0])
        while True:
            with self._conn.cursor() as cur:
                cur.execute("SELECT sequence_no FROM sync_inbox WHERE station_id = %s"
                            " AND sequence_no > %s ORDER BY sequence_no LIMIT 1000",
                            (station_id, actual))
                siguientes = [int(f[0]) for f in cur.fetchall()]
            avance = actual
            for numero in siguientes:
                if numero != avance + 1:
                    break
                avance = numero
            if avance == actual or len(siguientes) < 1000 or avance != siguientes[-1]:
                actual = avance
                break
            actual = avance
        self._exec("UPDATE sync_stations SET last_seen_at = %s, last_sequence = %s"
                   " WHERE id = %s", (now, actual, station_id))

    # ── transacciones ───────────────────────────────────────────────────
    @contextmanager
    def savepoint(self):
        with self._conn.transaction():
            yield

    def commit(self) -> None:
        self._conn.commit()

    def rollback(self) -> None:
        self._conn.rollback()

    # ── hechos ──────────────────────────────────────────────────────────
    def fact_hash(self, event_id: str) -> str | None:
        fila = self._one("SELECT content_hash FROM sync_inbox WHERE event_id = %s", (event_id,))
        return None if fila is None else str(fila[0])

    def event_for_sequence(self, station_id: str, sequence_no: int) -> str | None:
        fila = self._one("SELECT event_id FROM sync_inbox WHERE station_id = %s"
                         " AND sequence_no = %s", (station_id, sequence_no))
        return None if fila is None else str(fila[0])

    def insert_fact(self, envelope: ReplicationEnvelope, *, station_id: str, status: str,
                    error_code: str | None, now: datetime) -> bool:
        return self._exec(
            """INSERT INTO sync_inbox (event_id, station_id, sequence_no, content_hash,
               envelope_version, event_type, schema_version, aggregate_type, aggregate_id,
               aggregate_version, branch_id, operation_id, actor_id, correlation_id,
               causation_id, occurred_at, received_at, payload, "authorization", status,
               error_code, processed_at)
               VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
               ON CONFLICT (event_id) DO NOTHING""",
            (envelope.event_id, station_id, envelope.sequence_no, envelope.content_hash,
             envelope.envelope_version, envelope.event_type, envelope.schema_version,
             envelope.aggregate_type, envelope.aggregate_id, envelope.aggregate_version,
             envelope.branch_id, envelope.operation_id, envelope.actor_id,
             envelope.correlation_id, envelope.causation_id, envelope.occurred_at, now,
             json.dumps(dict(envelope.payload), ensure_ascii=False),
             json.dumps(dict(envelope.authorization), ensure_ascii=False), status,
             error_code, now)) == 1

    # ── agregados y conflictos ──────────────────────────────────────────
    def station_head(self, aggregate_type: str, aggregate_id: str,
                     station_id: str) -> int | None:
        fila = self._one(
            """SELECT MAX(aggregate_version) FROM sync_inbox
               WHERE aggregate_type = %s AND aggregate_id = %s AND station_id = %s
                 AND status = 'APPLIED'""", (aggregate_type, aggregate_id, station_id))
        return None if fila is None or fila[0] is None else int(fila[0])

    def advance_head(self, envelope: ReplicationEnvelope, *, station_id: str,
                     now: datetime) -> None:
        self._exec(
            """INSERT INTO sync_aggregate_heads (aggregate_type, aggregate_id, last_version,
               last_event_id, last_station_id, updated_at) VALUES (%s,%s,%s,%s,%s,%s)
               ON CONFLICT (aggregate_type, aggregate_id) DO UPDATE SET
                 last_version = EXCLUDED.last_version, last_event_id = EXCLUDED.last_event_id,
                 last_station_id = EXCLUDED.last_station_id, updated_at = EXCLUDED.updated_at""",
            (envelope.aggregate_type, envelope.aggregate_id, envelope.aggregate_version,
             envelope.event_id, station_id, now))

    def add_conflict(self, *, event_id: str, kind: str, details: Mapping[str, Any],
                     now: datetime) -> None:
        self._exec("INSERT INTO sync_conflicts (id, event_id, kind, details, created_at)"
                   " VALUES (%s, %s, %s, %s, %s)",
                   (new_uuid(), event_id, kind, json.dumps(dict(details), default=str), now))


__all__ = ["PostgresCentralInboxRepository"]
