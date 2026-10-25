"""Persistencia del motor de replicación único (Slice 2). Sin commits: la
frontera es `ReplicationUnitOfWork`."""

from __future__ import annotations

import json
from typing import Any

from backend.shared.ids import new_uuid

_STATES = ("PENDING", "IN_FLIGHT", "RETRY", "SYNCED", "CONFLICT", "DEAD")


def _rows(cursor) -> list[dict]:
    nombres = [c[0] for c in cursor.description]
    return [dict(zip(nombres, fila)) for fila in cursor.fetchall()]


def _row(cursor) -> dict | None:
    fila = cursor.fetchone()
    return None if fila is None else dict(zip((c[0] for c in cursor.description), fila))


class ReplicationRepository:
    def __init__(self, connection: Any) -> None:
        self._conn = connection

    # ── estaciones ──────────────────────────────────────────────────────
    def register_station(self, *, station_id: str, branch_id: str, now: str,
                         online: bool = True) -> None:
        self._conn.execute(
            """INSERT INTO replication_stations
               (id, branch_id, connectivity, sync_status, created_at, updated_at)
               VALUES (?,?,?, 'IDLE', ?, ?) ON CONFLICT(id) DO NOTHING""",
            (station_id, branch_id, "ONLINE" if online else "OFFLINE", now, now))

    def get_station(self, station_id: str) -> dict | None:
        return _row(self._conn.execute(
            "SELECT * FROM replication_stations WHERE id=?", (station_id,)))

    def set_connectivity(self, *, station_id: str, online: bool, now: str) -> None:
        cursor = self._conn.execute(
            "UPDATE replication_stations SET connectivity=?, updated_at=? WHERE id=?",
            ("ONLINE" if online else "OFFLINE", now, station_id))
        if cursor.rowcount != 1:
            raise LookupError("Estación de sincronización no encontrada")

    def next_sequence(self, station_id: str) -> int:
        """Reserva la siguiente secuencia de la estación (nunca se reutiliza)."""
        self._conn.execute(
            "UPDATE replication_stations SET local_sequence = local_sequence + 1 WHERE id=?",
            (station_id,))
        return int(self._conn.execute(
            "SELECT local_sequence FROM replication_stations WHERE id=?",
            (station_id,)).fetchone()[0])

    def finish_cycle(self, *, station_id: str, status: str, now: str,
                     error: str | None = None) -> None:
        self._conn.execute(
            """UPDATE replication_stations SET sync_status=?, last_error=?, last_sync_at=?,
               updated_at=?,
               last_synced_sequence = COALESCE((
                   SELECT MIN(sequence_no) - 1 FROM replication_envelopes
                   WHERE station_id = replication_stations.id AND state <> 'SYNCED'),
                   local_sequence)
               WHERE id=?""", (status, error, now, now, station_id))

    # ── sobres ──────────────────────────────────────────────────────────
    def next_aggregate_version(self, aggregate_type: str, aggregate_id: str) -> int:
        actual = self._conn.execute(
            "SELECT MAX(aggregate_version) FROM replication_envelopes"
            " WHERE aggregate_type=? AND aggregate_id=?", (aggregate_type, aggregate_id)
        ).fetchone()[0]
        return int(actual or 0) + 1

    def add(self, *, station_id: str, source: str, source_row_id: str, event_id: str,
            event_type: str, operation_id: str, sequence_no: int, aggregate_type: str,
            aggregate_id: str, aggregate_version: int, envelope_json: str,
            content_hash: str, now: str, state: str = "PENDING",
            last_error: str | None = None) -> str:
        identificador = new_uuid()
        self._conn.execute(
            """INSERT INTO replication_envelopes
               (id, station_id, source, source_row_id, event_id, event_type, operation_id,
                sequence_no, aggregate_type, aggregate_id, aggregate_version, envelope_json,
                content_hash, state, last_error, created_at)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (identificador, station_id, source, source_row_id, event_id, event_type,
             operation_id, sequence_no, aggregate_type, aggregate_id, aggregate_version,
             envelope_json, content_hash, state, last_error, now))
        return identificador

    def has_event(self, event_id: str) -> bool:
        return self._conn.execute("SELECT 1 FROM replication_envelopes WHERE event_id=?",
                                  (event_id,)).fetchone() is not None

    def recover_stale(self, *, station_id: str, claimed_before: str, now: str) -> int:
        """Sobres que quedaron EN VUELO por un cierre o caída: vuelven a RETRY.
        La entrega es «al menos una vez»; el servidor deduplica por event_id."""
        cursor = self._conn.execute(
            """UPDATE replication_envelopes SET state='RETRY', next_attempt_at=?,
               last_error='RECOVERED_AFTER_INTERRUPTION', claimed_at=NULL
               WHERE station_id=? AND state='IN_FLIGHT'
                 AND (claimed_at IS NULL OR claimed_at < ?)""",
            (now, station_id, claimed_before))
        return cursor.rowcount

    def claim_ready(self, *, station_id: str, now: str, limit: int) -> list[dict]:
        """Toma los sobres listos en orden de secuencia. Un agregado con un sobre
        en CONFLICTO o MUERTO no avanza (orden causal por agregado); los demás sí."""
        listos = _rows(self._conn.execute(
            """SELECT * FROM replication_envelopes e
               WHERE e.station_id=? AND e.state IN ('PENDING','RETRY')
                 AND (e.next_attempt_at IS NULL OR e.next_attempt_at <= ?)
                 AND NOT EXISTS (
                     SELECT 1 FROM replication_envelopes b
                     WHERE b.aggregate_type = e.aggregate_type
                       AND b.aggregate_id = e.aggregate_id
                       AND b.state IN ('CONFLICT','DEAD')
                       AND b.aggregate_version < e.aggregate_version)
               ORDER BY e.sequence_no LIMIT ?""", (station_id, now, limit)))
        tomados = []
        for fila in listos:
            cursor = self._conn.execute(
                """UPDATE replication_envelopes
                   SET state='IN_FLIGHT', attempt_count=attempt_count+1, claimed_at=?
                   WHERE id=? AND state IN ('PENDING','RETRY')""", (now, fila["id"]))
            if cursor.rowcount == 1:
                tomados.append({**fila, "attempt_count": fila["attempt_count"] + 1})
        return tomados

    def mark_synced(self, *, envelope_id: str, remote_revision: str, now: str) -> None:
        self._conn.execute(
            """UPDATE replication_envelopes SET state='SYNCED', remote_revision=?, synced_at=?,
               next_attempt_at=NULL, claimed_at=NULL, last_error=NULL
               WHERE id=? AND state='IN_FLIGHT'""", (remote_revision, now, envelope_id))

    def mark_retry(self, *, envelope_id: str, next_attempt_at: str, error: str) -> None:
        self._conn.execute(
            """UPDATE replication_envelopes SET state='RETRY', next_attempt_at=?, last_error=?,
               claimed_at=NULL WHERE id=? AND state='IN_FLIGHT'""",
            (next_attempt_at, error[:500], envelope_id))

    def mark_conflict(self, *, envelope_id: str, remote_revision: str, error: str,
                      conflict: dict | None) -> None:
        self._conn.execute(
            """UPDATE replication_envelopes SET state='CONFLICT', remote_revision=?,
               last_error=?, conflict_json=?, claimed_at=NULL
               WHERE id=? AND state='IN_FLIGHT'""",
            (remote_revision, error[:500], json.dumps(conflict or {}, ensure_ascii=False,
                                                       default=str), envelope_id))

    def mark_dead(self, *, envelope_id: str, error: str) -> None:
        self._conn.execute(
            """UPDATE replication_envelopes SET state='DEAD', last_error=?, claimed_at=NULL
               WHERE id=? AND state='IN_FLIGHT'""", (error[:500], envelope_id))

    def requeue(self, *, envelope_id: str, now: str) -> bool:
        """Reenvío controlado de un sobre en CONFLICTO o MUERTO. Se reenvía el
        MISMO sobre (misma huella): cambiarle la versión haría que el servidor
        viera el mismo event_id con otro contenido (EVENT_ID_REUSED)."""
        cursor = self._conn.execute(
            """UPDATE replication_envelopes SET state='RETRY', next_attempt_at=?,
               attempt_count=0, conflict_json=NULL, claimed_at=NULL
               WHERE id=? AND state IN ('CONFLICT','DEAD')""", (now, envelope_id))
        return cursor.rowcount == 1

    def settle_remote(self, *, envelope_id: str, now: str) -> bool:
        """Conflicto resuelto a favor del servidor: el sobre deja de enviarse."""
        cursor = self._conn.execute(
            """UPDATE replication_envelopes SET state='SYNCED', synced_at=?, conflict_json=NULL
               WHERE id=? AND state='CONFLICT'""", (now, envelope_id))
        return cursor.rowcount == 1

    def get(self, envelope_id: str) -> dict | None:
        return _row(self._conn.execute(
            "SELECT * FROM replication_envelopes WHERE id=?", (envelope_id,)))

    def counts(self, station_id: str, *, source: str | None = None) -> dict[str, int]:
        filtro, args = ("AND source=?", (station_id, source)) if source else ("", (station_id,))
        conteo = dict(self._conn.execute(
            f"SELECT state, COUNT(*) FROM replication_envelopes WHERE station_id=? {filtro}"
            " GROUP BY state", args).fetchall())
        return {estado: int(conteo.get(estado, 0)) for estado in _STATES}

    def list_recent(self, station_id: str, *, source: str | None = None,
                    states: tuple[str, ...] | None = None, limit: int = 100) -> list[dict]:
        condiciones, args = ["station_id=?"], [station_id]
        if source:
            condiciones.append("source=?")
            args.append(source)
        if states:
            condiciones.append(f"state IN ({','.join('?' * len(states))})")
            args.extend(states)
        args.append(limit)
        return _rows(self._conn.execute(
            f"""SELECT id, source, event_id, event_type, operation_id, aggregate_type,
                       aggregate_id, sequence_no, aggregate_version, state, attempt_count,
                       next_attempt_at, last_error, remote_revision, conflict_json,
                       created_at, synced_at
                FROM replication_envelopes WHERE {' AND '.join(condiciones)}
                ORDER BY sequence_no DESC LIMIT ?""", args))


__all__ = ["ReplicationRepository"]
