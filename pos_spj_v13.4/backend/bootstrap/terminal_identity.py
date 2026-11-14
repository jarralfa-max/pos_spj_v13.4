"""Quién es esta terminal, para la sesión (SDLC-ARQ-TERM-001).

La sesión, las ventas y el resto de consumidores reciben un UUIDv7 persistente,
no el hostname: renombrar el equipo ya no cambia la estación. El registro y la
regla de adopción viven en `SqliteTerminalIdentityRepository`.

Registrar la fila no debe impedir entrar a vender: si la escritura falla queda
en el log y la sesión sigue con el id, que ya es válido.
"""
from __future__ import annotations

import logging
import platform
import sqlite3
from datetime import datetime, timezone
from typing import Any

from backend.bootstrap.application_context import default_workstation_id
from backend.infrastructure.db.repositories.settings.terminal_identity_repository import (
    SqliteTerminalIdentityRepository,
    terminal_code,
)
from backend.infrastructure.db.sqlite_backup import database_schema_version
from backend.infrastructure.db.transaction import TransactionalUnitOfWork
from backend.shared.app_version import VERSION
from backend.shared.ids import is_uuidv7
from backend.shared.sync.replication_envelope import ENVELOPE_VERSION

logger = logging.getLogger("spj.bootstrap.terminal_identity")

DEFAULT_WORKSTATION_TYPE = "POS"


class _TerminalUnitOfWork(TransactionalUnitOfWork):
    def __init__(self, connection: Any) -> None:
        self.connection = connection
        self.terminal = SqliteTerminalIdentityRepository(connection)
        self._completed = False


def current_terminal_id(connection) -> str:
    """El id de esta terminal; `""` si la base no tiene el registro."""
    if not SqliteTerminalIdentityRepository(connection).available():
        return ""
    with _TerminalUnitOfWork(connection) as uow:
        return uow.terminal.ensure_id(default_workstation_id())


def register_terminal(connection, *, branch_id: str, workstation_type: str = "") -> str:
    """Asegura la fila de esta terminal en `workstations` para la sucursal anclada
    y refresca sus versiones. Devuelve su id. Sin sucursal sólo hay id."""
    terminal_id = current_terminal_id(connection)
    if not terminal_id or not is_uuidv7(branch_id):
        return terminal_id
    try:
        with _TerminalUnitOfWork(connection) as uow:
            uow.terminal.register(
                terminal_id=terminal_id, branch_id=branch_id,
                hostname=default_workstation_id(),
                workstation_type=workstation_type or DEFAULT_WORKSTATION_TYPE,
                operating_system=platform.platform(), app_version=VERSION,
                schema_version=str(database_schema_version(connection) or ""),
                protocol_version=str(ENVELOPE_VERSION),
                now=datetime.now(timezone.utc).isoformat())
    except sqlite3.Error:
        logger.exception("No se pudo registrar la terminal %s", terminal_id)
    return terminal_id


def terminal_label(workstation_id: str) -> str:
    """Lo que ve una persona: el código de la terminal, no un UUID completo."""
    return terminal_code(workstation_id) if is_uuidv7(workstation_id) else workstation_id


__all__ = ["DEFAULT_WORKSTATION_TYPE", "current_terminal_id", "register_terminal",
           "terminal_label"]
