"""Recarga de permisos de una sesión abierta (auditoría de permisos 968e0bc, PER-08).

Antes los permisos se cargaban UNA vez al iniciar sesión: retirar un permiso
crítico, cambiar el rol de alguien o desactivar su cuenta no tenía efecto en
las terminales donde ya estaba dentro hasta que cerrara sesión.

Ahora cada cambio de concesión sube `security_grant_versions` (en la misma
transacción que el cambio). La sesión pregunta por esa versión como mucho cada
`interval` segundos; si cambió, vuelve a resolver sus permisos con la MISMA
`PermissionQueryService` del inicio de sesión. Una cuenta desactivada (o
borrada) devuelve `None`: la sesión queda revocada, administrador incluido.
"""

from __future__ import annotations

import time

from backend.application.security.permission_query_service import PermissionQueryService
from backend.infrastructure.db.repositories.security.grant_version_repository import (
    SqliteGrantVersionRepository,
)
from backend.infrastructure.db.repositories.security.permission_repository import (
    SqlitePermissionRepository,
)

DEFAULT_INTERVAL_SECONDS = 3.0


class SessionGrantRefresher:
    def __init__(self, connection, *, interval: float = DEFAULT_INTERVAL_SECONDS,
                 clock=time.monotonic) -> None:
        self._conn = connection
        self._versions = SqliteGrantVersionRepository(connection)
        self._interval = interval
        self._clock = clock
        self._seen = self._versions.current()
        self._checked_at = clock()

    def changed(self) -> bool:
        """¿Cambió alguna concesión desde la última vez? Barato: una fila."""
        ahora = self._clock()
        if ahora - self._checked_at < self._interval:
            return False
        self._checked_at = ahora
        try:
            actual = self._versions.current()
        except Exception:  # noqa: BLE001 - una lectura fallida no tumba la sesión
            return False
        if actual == self._seen:
            return False
        self._seen = actual
        return True

    def load(self, user_id: str, branch_id: str | None) -> frozenset[str] | None:
        """Permisos vigentes, o `None` si la cuenta ya no está activa."""
        if not self._user_is_active(user_id):
            return None
        return PermissionQueryService(
            SqlitePermissionRepository(self._conn)).permission_codes_for_user(user_id, branch_id)

    def _user_is_active(self, user_id: str) -> bool:
        row = self._conn.execute(
            "SELECT COALESCE(activo, 1) FROM usuarios WHERE id=?", (str(user_id),)).fetchone()
        return bool(row and int(row[0]) == 1)


__all__ = ["DEFAULT_INTERVAL_SECONDS", "SessionGrantRefresher"]
