"""p006 — Aprovisionamiento de equipos (auditoría enterprise, Fase 4; decisión D3).

* `sync_stations` gana la identidad de equipo: llave pública Ed25519 (la privada
  nunca sale del equipo), tipo de estación, capacidades, versión instalada,
  última sincronización, eventos pendientes que reporta, si es estación de
  ADMINISTRACIÓN (puede gestionar equipos) y con qué estación fue reemplazada.
  `credential_hash` queda para el secreto del Slice 4 (respaldo de transición);
  un equipo vinculado por invitación lleva `'!'`, que ninguna huella iguala.
* `device_invitations`: invitación de UN solo uso y vida corta. Sólo se guarda la
  huella SHA-256 del código. Tipos: NEW (equipo nuevo), REPLACEMENT (otro equipo
  toma el lugar de uno perdido o robado: nueva identidad, la vieja queda dada de
  baja con `replaced_by`), RECOVERY (el mismo equipo reinstalado: misma
  identidad, llave nueva, retoma su secuencia). Nadie toma una identidad
  existente sin una invitación de reemplazo o recuperación.
* `central_device_events`: historial de cada equipo (vinculación, suspensión,
  reactivación, baja, reasignación, reemplazo, recuperación, invitaciones).

Sólo agrega. Idempotente.
"""

from __future__ import annotations

DDL = (
    "ALTER TABLE sync_stations ADD COLUMN IF NOT EXISTS public_key TEXT",
    "ALTER TABLE sync_stations ADD COLUMN IF NOT EXISTS key_algorithm TEXT",
    "ALTER TABLE sync_stations ADD COLUMN IF NOT EXISTS workstation_type TEXT",
    "ALTER TABLE sync_stations ADD COLUMN IF NOT EXISTS capabilities TEXT[] NOT NULL"
    " DEFAULT '{}'",
    "ALTER TABLE sync_stations ADD COLUMN IF NOT EXISTS app_version TEXT",
    "ALTER TABLE sync_stations ADD COLUMN IF NOT EXISTS last_sync_at TIMESTAMPTZ",
    "ALTER TABLE sync_stations ADD COLUMN IF NOT EXISTS pending_events INTEGER",
    "ALTER TABLE sync_stations ADD COLUMN IF NOT EXISTS is_admin_station BOOLEAN NOT NULL"
    " DEFAULT FALSE",
    "ALTER TABLE sync_stations ADD COLUMN IF NOT EXISTS replaced_by UUID",
    "ALTER TABLE sync_stations ADD COLUMN IF NOT EXISTS enrolled_via UUID",
    """
    CREATE TABLE IF NOT EXISTS device_invitations (
        id                 UUID PRIMARY KEY,
        token_hash         TEXT NOT NULL UNIQUE,
        kind               TEXT NOT NULL CHECK (kind IN ('NEW', 'REPLACEMENT', 'RECOVERY')),
        branch_id          UUID NOT NULL,
        workstation_type   TEXT NOT NULL,
        capabilities       TEXT[] NOT NULL DEFAULT '{}',
        display_name       TEXT NOT NULL DEFAULT '',
        grants_admin       BOOLEAN NOT NULL DEFAULT FALSE,
        target_station_id  UUID,
        created_by_station UUID,
        created_by_user    UUID,
        created_at         TIMESTAMPTZ NOT NULL,
        expires_at         TIMESTAMPTZ NOT NULL,
        status             TEXT NOT NULL DEFAULT 'PENDING'
                           CHECK (status IN ('PENDING', 'CONSUMED', 'REVOKED')),
        consumed_at        TIMESTAMPTZ,
        consumed_station_id UUID,
        CHECK (expires_at > created_at),
        CHECK ((kind = 'NEW') = (target_station_id IS NULL)),
        CHECK ((status = 'CONSUMED') = (consumed_at IS NOT NULL))
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS central_device_events (
        id            BIGSERIAL PRIMARY KEY,
        station_id    UUID,
        invitation_id UUID,
        event         TEXT NOT NULL,
        actor_station UUID,
        actor_user    UUID,
        detail        JSONB NOT NULL DEFAULT '{}',
        occurred_at   TIMESTAMPTZ NOT NULL
    )
    """,
    "CREATE INDEX IF NOT EXISTS ix_central_device_events_station"
    " ON central_device_events (station_id, occurred_at)",
)


def run(conn) -> None:
    with conn.cursor() as cur:
        for sentencia in DDL:
            cur.execute(sentencia)


up = run
