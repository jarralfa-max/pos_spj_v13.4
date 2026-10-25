"""350 — Motor de replicación único (arquitectura híbrida, Slice 2).

1. Crea `replication_stations` y `replication_envelopes`.
2. Traslada las estaciones de Caja (`cash_sync_devices`) conservando su id,
   sucursal y conectividad. Sus sobres viejos NO se copian: el motor nuevo los
   vuelve a preparar desde `cash_outbox` (cada hecho conserva su `event_id`, así
   que el servidor deduplica lo que ya hubiera recibido; nunca hubo transporte
   configurado, así que en la práctica no recibió nada).
3. REPARA lo que el motor viejo de Caja dañó. Al reintentar o al marcar un
   conflicto escribía `cash_outbox.status='FAILED'`, y el despachador que lleva
   la Caja a Finanzas sólo toma filas PENDING: esos movimientos nunca llegaban
   a contabilidad. Sólo se tocan filas cuyo `last_error` es del motor de
   sincronización:
   - sin `dispatched_at` (Finanzas nunca las recibió) → vuelven a PENDING;
   - con `dispatched_at` (Finanzas ya las había recibido) → vuelven a DISPATCHED.

Las tablas `cash_sync_*` se conservan (expandir/migrar/contraer): ya nadie
escribe en ellas; se retiran en una migración posterior. Idempotente.
"""

from __future__ import annotations

import logging

logger = logging.getLogger("spj.migrations.350")

#: `last_error` que sólo escribía el motor de sincronización de CASH-19.
_SYNC_ERRORS = ("TRANSPORT_UNAVAILABLE", "SYNC_CONFLICT", "CONFLICT_RETRY",
                "SYNC_RETRY_PENDING")


def _table(conn, name: str) -> bool:
    return conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
                        (name,)).fetchone() is not None


#: Estados de un sobre: PENDING → IN_FLIGHT → SYNCED | RETRY | CONFLICT | DEAD. Cada
#: sobre lleva su PROPIO estado: nunca se toca el `status` del outbox de origen.
_DDL = (
    """
    CREATE TABLE IF NOT EXISTS replication_stations (
        id TEXT NOT NULL PRIMARY KEY,
        branch_id TEXT NOT NULL,
        local_sequence INTEGER NOT NULL DEFAULT 0 CHECK (local_sequence >= 0),
        last_synced_sequence INTEGER NOT NULL DEFAULT 0 CHECK (last_synced_sequence >= 0),
        connectivity TEXT NOT NULL DEFAULT 'ONLINE'
            CHECK (connectivity IN ('ONLINE','OFFLINE')),
        sync_status TEXT NOT NULL DEFAULT 'IDLE'
            CHECK (sync_status IN ('IDLE','SYNCING','RETRYING','CONFLICT','ERROR')),
        last_error TEXT,
        last_sync_at TEXT,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS replication_envelopes (
        id TEXT NOT NULL PRIMARY KEY,
        station_id TEXT NOT NULL REFERENCES replication_stations(id),
        source TEXT NOT NULL,
        source_row_id TEXT NOT NULL,
        event_id TEXT NOT NULL UNIQUE,
        event_type TEXT NOT NULL,
        operation_id TEXT NOT NULL,
        sequence_no INTEGER NOT NULL CHECK (sequence_no >= 1),
        aggregate_type TEXT NOT NULL,
        aggregate_id TEXT NOT NULL,
        aggregate_version INTEGER NOT NULL CHECK (aggregate_version >= 1),
        envelope_json TEXT NOT NULL,
        content_hash TEXT NOT NULL,
        state TEXT NOT NULL DEFAULT 'PENDING'
            CHECK (state IN ('PENDING','IN_FLIGHT','RETRY','SYNCED','CONFLICT','DEAD')),
        attempt_count INTEGER NOT NULL DEFAULT 0 CHECK (attempt_count >= 0),
        next_attempt_at TEXT,
        claimed_at TEXT,
        last_error TEXT,
        remote_revision TEXT,
        conflict_json TEXT,
        created_at TEXT NOT NULL,
        synced_at TEXT,
        UNIQUE (source, source_row_id),
        UNIQUE (station_id, sequence_no)
    )
    """,
    "CREATE INDEX IF NOT EXISTS ix_replication_envelopes_ready"
    " ON replication_envelopes (station_id, state, next_attempt_at, sequence_no)",
    "CREATE INDEX IF NOT EXISTS ix_replication_envelopes_aggregate"
    " ON replication_envelopes (aggregate_type, aggregate_id, aggregate_version)",
)


def run(conn) -> None:
    for sentencia in _DDL:
        conn.execute(sentencia)
    trasladadas = 0
    if _table(conn, "cash_sync_devices"):
        for fila in conn.execute(
                "SELECT id, branch_id, connectivity, updated_at FROM cash_sync_devices"
        ).fetchall():
            momento = fila[3] or "1970-01-01T00:00:00+00:00"
            cursor = conn.execute(
                """INSERT INTO replication_stations
                   (id, branch_id, connectivity, sync_status, created_at, updated_at)
                   VALUES (?,?,?, 'IDLE', ?, ?) ON CONFLICT(id) DO NOTHING""",
                (fila[0], fila[1], fila[2] if fila[2] in ("ONLINE", "OFFLINE") else "ONLINE",
                 momento, momento))
            trasladadas += max(cursor.rowcount or 0, 0)
    reparadas = restauradas = 0
    if _table(conn, "cash_outbox"):
        marcas = ",".join("?" * len(_SYNC_ERRORS))
        reparadas = conn.execute(
            f"""UPDATE cash_outbox SET status='PENDING', last_error=NULL, next_attempt_at=NULL
                WHERE status='FAILED' AND dispatched_at IS NULL AND last_error IN ({marcas})""",
            _SYNC_ERRORS).rowcount
        restauradas = conn.execute(
            f"""UPDATE cash_outbox SET status='DISPATCHED', last_error=NULL
                WHERE status='FAILED' AND dispatched_at IS NOT NULL
                  AND last_error IN ({marcas})""", _SYNC_ERRORS).rowcount
    conn.commit()
    logger.info("350: estaciones trasladadas=%s; cash_outbox devueltos a Finanzas=%s, "
                "restaurados como despachados=%s", trasladadas, reparadas, restauradas)


up = run
