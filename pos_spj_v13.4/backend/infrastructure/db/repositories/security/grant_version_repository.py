"""Versión de las concesiones de permiso (auditoría de permisos 968e0bc, PER-08).

Sube cada vez que cambia una concesión de rol o una excepción de usuario. Una
sesión abierta la consulta de vez en cuando y, si cambió, recarga sus permisos:
antes una revocación urgente sólo surtía efecto cuando el usuario volvía a
iniciar sesión.

La tabla nace en la migración 347; en una base anterior la versión es siempre 0
y subirla no hace nada (la sesión se comporta como antes).
"""

from __future__ import annotations

from backend.infrastructure.db.repositories.security.base import SecurityRepositoryBase

_TABLE = "security_grant_versions"
_SCOPE = "global"


class SqliteGrantVersionRepository(SecurityRepositoryBase):
    def current(self) -> int:
        if not self._table_exists(_TABLE):
            return 0
        row = self._query_one(f"SELECT version FROM {_TABLE} WHERE scope=?", (_SCOPE,))
        return int(row["version"]) if row is not None else 0

    def bump(self) -> None:
        """Dentro de la transacción del caso de uso: no confirma."""
        if not self._table_exists(_TABLE):
            return
        self._conn.execute(
            f"INSERT OR IGNORE INTO {_TABLE} (scope, version) VALUES (?, 0)", (_SCOPE,))
        self._conn.execute(
            f"UPDATE {_TABLE} SET version = version + 1,"
            " updated_at = strftime('%Y-%m-%dT%H:%M:%SZ','now') WHERE scope=?", (_SCOPE,))
