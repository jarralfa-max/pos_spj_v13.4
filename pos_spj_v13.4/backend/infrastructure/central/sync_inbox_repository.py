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
    _STATION_COLS = ("id, branch_id, credential_hash, status, last_sequence, display_name,"
                     " public_key, key_algorithm, workstation_type, capabilities, app_version,"
                     " last_seen_at, last_sync_at, pending_events, is_admin_station,"
                     " replaced_by, created_at, retired_at")

    @staticmethod
    def _station(fila) -> dict:
        return {"id": str(fila[0]), "branch_id": str(fila[1]), "credential_hash": fila[2],
                "status": fila[3], "last_sequence": int(fila[4]), "display_name": fila[5],
                "public_key": fila[6], "key_algorithm": fila[7], "workstation_type": fila[8],
                "capabilities": list(fila[9] or ()), "app_version": fila[10],
                "last_seen_at": fila[11], "last_sync_at": fila[12], "pending_events": fila[13],
                "is_admin_station": bool(fila[14]),
                "replaced_by": str(fila[15]) if fila[15] else None,
                "created_at": fila[16], "retired_at": fila[17]}

    def get_station(self, station_id: str) -> Mapping[str, Any] | None:
        fila = self._one(f"SELECT {self._STATION_COLS} FROM sync_stations WHERE id = %s",
                         (station_id,))
        return None if fila is None else self._station(fila)

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

    # ── registro de equipos (auditoría enterprise, Fase 4; p006) ────────
    def list_stations(self) -> list[Mapping[str, Any]]:
        with self._conn.cursor() as cur:
            cur.execute(f"SELECT {self._STATION_COLS} FROM sync_stations"
                        " ORDER BY status, display_name, created_at")
            return [self._station(f) for f in cur.fetchall()]

    def insert_invitation(self, row: Mapping[str, Any]) -> None:
        self._exec(
            "INSERT INTO device_invitations (id, token_hash, kind, branch_id, workstation_type,"
            " capabilities, display_name, grants_admin, target_station_id, created_by_station,"
            " created_by_user, created_at, expires_at)"
            " VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
            (row["id"], row["token_hash"], row["kind"], row["branch_id"],
             row["workstation_type"], list(row["capabilities"]), row["display_name"],
             row["grants_admin"], row["target_station_id"], row["created_by_station"],
             row["created_by_user"], row["created_at"], row["expires_at"]))

    _INV_COLS = ("id, token_hash, kind, branch_id, workstation_type, capabilities, display_name,"
                 " grants_admin, target_station_id, created_by_station, created_by_user,"
                 " created_at, expires_at, status, consumed_at, consumed_station_id")

    @staticmethod
    def _invitation(f) -> dict:
        return {"id": str(f[0]), "token_hash": f[1], "kind": f[2], "branch_id": str(f[3]),
                "workstation_type": f[4], "capabilities": list(f[5] or ()),
                "display_name": f[6], "grants_admin": bool(f[7]),
                "target_station_id": str(f[8]) if f[8] else None,
                "created_by_station": str(f[9]) if f[9] else None,
                "created_by_user": str(f[10]) if f[10] else None, "created_at": f[11],
                "expires_at": f[12], "status": f[13], "consumed_at": f[14],
                "consumed_station_id": str(f[15]) if f[15] else None}

    def invitation_by_hash(self, token_hash: str) -> Mapping[str, Any] | None:
        fila = self._one(f"SELECT {self._INV_COLS} FROM device_invitations"
                         " WHERE token_hash = %s", (token_hash,))
        return None if fila is None else self._invitation(fila)

    def consume_invitation(self, invitation_id: str, *, station_id: str,
                           now: datetime) -> bool:
        """Atómico: sólo una solicitud consume el código (la otra ve 0 filas)."""
        return self._exec(
            "UPDATE device_invitations SET status = 'CONSUMED', consumed_at = %s,"
            " consumed_station_id = %s WHERE id = %s AND status = 'PENDING'"
            " AND expires_at > %s", (now, station_id, invitation_id, now)) == 1

    def revoke_invitation(self, invitation_id: str) -> bool:
        return self._exec("UPDATE device_invitations SET status = 'REVOKED'"
                          " WHERE id = %s AND status = 'PENDING'", (invitation_id,)) == 1

    def list_invitations(self, *, now: datetime) -> list[Mapping[str, Any]]:
        with self._conn.cursor() as cur:
            cur.execute(f"SELECT {self._INV_COLS} FROM device_invitations"
                        " ORDER BY created_at DESC LIMIT 200")
            return [self._invitation(f) for f in cur.fetchall()]

    def register_device_station(self, *, station_id: str, branch_id: str, display_name: str,
                                public_key: str, workstation_type: str, capabilities,
                                is_admin: bool, invitation_id: str) -> None:
        self._exec(
            "INSERT INTO sync_stations (id, branch_id, display_name, credential_hash,"
            " public_key, key_algorithm, workstation_type, capabilities, is_admin_station,"
            " enrolled_via) VALUES (%s,%s,%s,'!',%s,'ed25519',%s,%s,%s,%s)",
            (station_id, branch_id, display_name, public_key, workstation_type,
             list(capabilities), bool(is_admin), invitation_id))

    def rotate_station_key(self, station_id: str, *, public_key: str,
                           invitation_id: str) -> None:
        self._exec("UPDATE sync_stations SET public_key = %s, key_algorithm = 'ed25519',"
                   " enrolled_via = %s WHERE id = %s", (public_key, invitation_id, station_id))

    def mark_replaced(self, station_id: str, *, replaced_by: str, now: datetime) -> None:
        self._exec("UPDATE sync_stations SET status = 'RETIRED', replaced_by = %s,"
                   " retired_at = COALESCE(retired_at, %s) WHERE id = %s",
                   (replaced_by, now, station_id))

    def reassign_station(self, station_id: str, *, branch_id: str) -> None:
        self._exec("UPDATE sync_stations SET branch_id = %s WHERE id = %s",
                   (branch_id, station_id))

    def report_heartbeat(self, station_id: str, *, app_version, pending_events,
                         last_sync_at, now: datetime) -> None:
        self._exec("UPDATE sync_stations SET app_version = COALESCE(%s, app_version),"
                   " pending_events = %s, last_sync_at = COALESCE(%s, last_sync_at),"
                   " last_seen_at = %s WHERE id = %s",
                   (app_version, pending_events, last_sync_at, now, station_id))

    def add_device_event(self, *, station_id, invitation_id, event, actor_station, actor_user,
                         detail, now: datetime) -> None:
        import json
        self._exec("INSERT INTO central_device_events (station_id, invitation_id, event,"
                   " actor_station, actor_user, detail, occurred_at)"
                   " VALUES (%s,%s,%s,%s,%s,%s::jsonb,%s)",
                   (station_id, invitation_id, event, actor_station, actor_user,
                    json.dumps(dict(detail), default=str), now))

    def device_events(self, station_id: str) -> list[Mapping[str, Any]]:
        with self._conn.cursor() as cur:
            cur.execute("SELECT event, actor_station, actor_user, detail, occurred_at,"
                        " invitation_id FROM central_device_events WHERE station_id = %s"
                        " ORDER BY occurred_at, id", (station_id,))
            return [{"event": f[0], "actor_station": str(f[1]) if f[1] else None,
                     "actor_user": str(f[2]) if f[2] else None, "detail": f[3],
                     "occurred_at": f[4], "invitation_id": str(f[5]) if f[5] else None}
                    for f in cur.fetchall()]

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
