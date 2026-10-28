"""354 — Vinculación de ESTE equipo con el servidor central (auditoría enterprise,
Fase 4; decisión D3).

`device_enrollment` guarda la identidad que el central le dio a esta estación al
vincularse con un código de invitación: id UUIDv7, sitio, tipo, capacidades, si
administra equipos, URL del central y la llave PÚBLICA. La privada vive en el
almacén de secretos del sistema (Credential Manager / DPAPI), nunca aquí.

`status`: ENROLLED (opera), SUSPENDED o REVOKED (lo informó el central: un
equipo dado de baja no abre sesión), SUPERSEDED (una vinculación posterior la
reemplazó en este equipo; queda como historia).

Sólo agrega una tabla. Idempotente.
"""

from __future__ import annotations

_DDL = (
    """
    CREATE TABLE IF NOT EXISTS device_enrollment (
        station_id TEXT NOT NULL PRIMARY KEY,
        central_url TEXT NOT NULL,
        branch_id TEXT NOT NULL,
        workstation_type TEXT NOT NULL,
        capabilities_json TEXT NOT NULL DEFAULT '[]',
        is_admin_station INTEGER NOT NULL DEFAULT 0 CHECK (is_admin_station IN (0, 1)),
        public_key TEXT NOT NULL,
        status TEXT NOT NULL DEFAULT 'ENROLLED'
            CHECK (status IN ('ENROLLED', 'SUSPENDED', 'REVOKED', 'SUPERSEDED')),
        replaced_station_id TEXT,
        enrolled_by TEXT,
        enrolled_at TEXT NOT NULL,
        last_contact_at TEXT,
        last_error TEXT
    )
    """,
    "CREATE INDEX IF NOT EXISTS ix_device_enrollment_status ON device_enrollment(status)",
)


def run(conn) -> None:
    for sentencia in _DDL:
        conn.execute(sentencia)
    conn.commit()


up = run
