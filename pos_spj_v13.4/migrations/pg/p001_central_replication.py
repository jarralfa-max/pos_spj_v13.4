"""p001 — Esquema central de replicación (PostgreSQL; arquitectura híbrida, Slice 3).

Lo mínimo para que el servidor reciba los sobres de las estaciones (la lógica de
ingesta es el Slice 4):

* `sync_stations`: estaciones autorizadas a enviar. La credencial se guarda como
  huella (nunca en claro); una estación dada de baja deja de poder enviar.
* `sync_inbox`: un renglón por hecho recibido. `event_id` es la clave de
  idempotencia del transporte (PRIMARY KEY: el mismo hecho no se aplica dos
  veces); `content_hash` detecta el mismo `event_id` con otro contenido
  (conflicto, nunca sobrescritura); `(station_id, sequence_no)` es único y
  permite detectar huecos de secuencia.
* `sync_aggregate_heads`: última versión aplicada de cada agregado, para el
  orden causal por agregado.
* `sync_conflicts`: lo que requiere decisión humana; nada financiero se corrige
  en silencio.

Tipos nativos (§5.2): UUID para identidad (los UUIDv7 los genera la capa
canónica, sin valores por omisión en la base), TIMESTAMPTZ para instantes,
JSONB para cargas auditables y BIGINT para ordinales. Ninguna columna
autoincremental y ningún REAL/FLOAT. Idempotente.
"""

from __future__ import annotations

DDL = (
    """
    CREATE TABLE IF NOT EXISTS sync_stations (
        id                UUID PRIMARY KEY,
        branch_id         UUID NOT NULL,
        display_name      TEXT NOT NULL DEFAULT '',
        credential_hash   TEXT NOT NULL,
        status            TEXT NOT NULL DEFAULT 'ACTIVE'
                          CHECK (status IN ('ACTIVE', 'SUSPENDED', 'RETIRED')),
        last_sequence     BIGINT NOT NULL DEFAULT 0 CHECK (last_sequence >= 0),
        last_seen_at      TIMESTAMPTZ,
        created_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
        retired_at        TIMESTAMPTZ,
        CHECK (status <> 'RETIRED' OR retired_at IS NOT NULL)
    )
    """,
    "CREATE INDEX IF NOT EXISTS ix_sync_stations_branch ON sync_stations (branch_id)",
    """
    CREATE TABLE IF NOT EXISTS sync_inbox (
        event_id          UUID PRIMARY KEY,
        station_id        UUID NOT NULL REFERENCES sync_stations (id),
        sequence_no       BIGINT NOT NULL CHECK (sequence_no >= 1),
        content_hash      CHAR(64) NOT NULL,
        envelope_version  SMALLINT NOT NULL CHECK (envelope_version >= 1),
        event_type        TEXT NOT NULL,
        schema_version    INTEGER NOT NULL CHECK (schema_version >= 1),
        aggregate_type    TEXT NOT NULL,
        aggregate_id      UUID NOT NULL,
        aggregate_version BIGINT NOT NULL CHECK (aggregate_version >= 0),
        branch_id         UUID NOT NULL,
        operation_id      UUID NOT NULL,
        actor_id          UUID,
        correlation_id    UUID,
        causation_id      UUID,
        occurred_at       TIMESTAMPTZ NOT NULL,
        received_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
        payload           JSONB NOT NULL,
        "authorization"   JSONB NOT NULL DEFAULT '{}'::jsonb,
        status            TEXT NOT NULL
                          CHECK (status IN ('APPLIED', 'CONFLICT', 'REJECTED')),
        error_code        TEXT,
        processed_at      TIMESTAMPTZ,
        CONSTRAINT uq_sync_inbox_station_sequence UNIQUE (station_id, sequence_no),
        CHECK (status = 'APPLIED' OR error_code IS NOT NULL)
    )
    """,
    "CREATE INDEX IF NOT EXISTS ix_sync_inbox_aggregate"
    " ON sync_inbox (aggregate_type, aggregate_id, aggregate_version)",
    "CREATE INDEX IF NOT EXISTS ix_sync_inbox_branch_time ON sync_inbox (branch_id, occurred_at)",
    "CREATE INDEX IF NOT EXISTS ix_sync_inbox_status ON sync_inbox (status) WHERE status <> 'APPLIED'",
    """
    CREATE TABLE IF NOT EXISTS sync_aggregate_heads (
        aggregate_type    TEXT NOT NULL,
        aggregate_id      UUID NOT NULL,
        last_version      BIGINT NOT NULL CHECK (last_version >= 0),
        last_event_id     UUID NOT NULL REFERENCES sync_inbox (event_id),
        updated_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
        PRIMARY KEY (aggregate_type, aggregate_id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS sync_conflicts (
        id                UUID PRIMARY KEY,
        event_id          UUID NOT NULL REFERENCES sync_inbox (event_id),
        kind              TEXT NOT NULL,
        details           JSONB NOT NULL DEFAULT '{}'::jsonb,
        status            TEXT NOT NULL DEFAULT 'OPEN' CHECK (status IN ('OPEN', 'RESOLVED')),
        resolution        TEXT,
        resolved_by       UUID,
        created_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
        resolved_at       TIMESTAMPTZ,
        CHECK (status = 'OPEN' OR (resolution IS NOT NULL AND resolved_by IS NOT NULL
                                   AND resolved_at IS NOT NULL))
    )
    """,
    "CREATE INDEX IF NOT EXISTS ix_sync_conflicts_open ON sync_conflicts (status, created_at)"
    " WHERE status = 'OPEN'",
)

TABLES = ("sync_stations", "sync_inbox", "sync_aggregate_heads", "sync_conflicts")


def run(conn) -> None:
    with conn.cursor() as cur:
        for sentencia in DDL:
            cur.execute(sentencia)


up = run
