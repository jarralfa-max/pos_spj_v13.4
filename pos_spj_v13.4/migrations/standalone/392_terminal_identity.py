"""392 — identidad persistente de la terminal (SDLC-ARQ-TERM-001).

`workstations` es la fuente canónica (decisión 2026-11-02). Esta migración:

* agrega `schema_version` y `protocol_version` a `workstations` (ya tenía
  estado, tipo, sucursal y `application_version`);
* fija el id de ESTA terminal en `configuraciones.terminal_instalacion_id`. Si ya
  hay una fila que representa a esta máquina, la adopta; si no, genera un UUIDv7.
  Su fila nace al primer login anclado;
* mueve los ajustes de actualización de esta máquina de la llave por hostname
  (`software_station_settings.workstation_key`) al id de la terminal. La bitácora
  `software_update_events` no se reescribe: es de sólo agregar.

Sólo agrega. Idempotente. Lo que dependía del hostname deja de hacerlo.

Reversa: borrar la clave `terminal_instalacion_id`, devolver `workstation_key`
al hostname y borrar la versión 392 de `schema_migrations`. Las dos columnas
pueden quedarse; nadie las lee sin la clave.
"""

from __future__ import annotations

import logging
import socket

from backend.infrastructure.db.repositories.settings.terminal_identity_repository import (
    SqliteTerminalIdentityRepository,
)

logger = logging.getLogger("spj.migrations.392")


def _hostname() -> str:
    try:
        return socket.gethostname() or ""
    except OSError:
        return ""


def _tabla(conn, nombre: str) -> bool:
    return conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
                        (nombre,)).fetchone() is not None


def run(conn) -> None:
    if not _tabla(conn, "workstations"):
        logger.info("392: sin registro de estaciones; nada que hacer.")
        return
    columnas = {fila[1] for fila in conn.execute("PRAGMA table_info(workstations)")}
    for columna in ("schema_version", "protocol_version"):
        if columna not in columnas:
            conn.execute(f"ALTER TABLE workstations ADD COLUMN {columna} TEXT")
    if _tabla(conn, "configuraciones"):
        hostname = _hostname()
        terminal_id = SqliteTerminalIdentityRepository(conn).ensure_id(hostname)
        if hostname and _tabla(conn, "software_station_settings"):
            conn.execute(
                "UPDATE software_station_settings SET workstation_key=?"
                " WHERE workstation_key=? AND NOT EXISTS (SELECT 1 FROM"
                " software_station_settings s WHERE s.workstation_key=?)",
                (terminal_id, hostname, terminal_id))
    conn.commit()
    logger.info("392: identidad de terminal lista.")


up = run
