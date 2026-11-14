"""Identidad de ESTA terminal (SDLC-ARQ-TERM-001).

`workstations` es la fuente canónica (decisión 2026-11-02). La clave
`terminal_instalacion_id` de `configuraciones` dice cuál de sus filas es esta
máquina, igual que `sucursal_instalacion_id` dice a qué sucursal está anclada:
el id se genera una vez y no depende del hostname, que queda sólo como dato
descriptivo en `device_identifier`.

Sin ancla no puede haber fila (`workstations.branch_id` es obligatorio): la
terminal ya tiene id, y su fila nace al primer login anclado.

Repositorio sin commit: la unidad de trabajo es la dueña.
"""

from __future__ import annotations

from backend.infrastructure.db.repositories.settings.base import SettingsRepositoryBase
from backend.shared.ids import new_uuid

TERMINAL_ID_KEY = "terminal_instalacion_id"
_VERSION_COLUMNS = {"schema_version", "protocol_version"}


def terminal_code(terminal_id: str) -> str:
    """Código legible de la terminal: el mismo en Estaciones y en la barra."""
    return f"TERM-{terminal_id[-8:].upper()}"


class SqliteTerminalIdentityRepository(SettingsRepositoryBase):
    def available(self) -> bool:
        """¿Tiene esta base el registro de terminales? (la migración 392 lo deja
        listo; las bases reducidas de algunas pruebas no lo tienen)."""
        tablas = {fila["name"] for fila in self._query(
            "SELECT name FROM sqlite_master WHERE type='table'"
            " AND name IN ('configuraciones','workstations')")}
        if tablas != {"configuraciones", "workstations"}:
            return False
        columnas = {fila["name"] for fila in self._query(
            "SELECT name FROM pragma_table_info('workstations')")}
        return _VERSION_COLUMNS <= columnas

    def stored_id(self) -> str | None:
        fila = self._query_one("SELECT valor FROM configuraciones WHERE clave=?",
                               (TERMINAL_ID_KEY,))
        return str(fila["valor"]) if fila and fila["valor"] else None

    def ensure_id(self, hostname: str) -> str:
        """El id de esta terminal; lo genera sólo la primera vez."""
        actual = self.stored_id()
        if actual:
            return actual
        terminal_id = self._adoptable(hostname) or new_uuid()
        self._execute("INSERT INTO configuraciones (clave, valor) VALUES (?, ?)"
                      " ON CONFLICT(clave) DO UPDATE SET valor = excluded.valor",
                      (TERMINAL_ID_KEY, terminal_id))
        return terminal_id

    def _adoptable(self, hostname: str) -> str | None:
        """Fila ya existente que representa a esta máquina: la que trae su nombre o,
        si no, la única activa sin máquina asociada (la crea la pantalla de cliente
        y sus preferencias cuelgan de ella). Nunca una que nombre a otra máquina."""
        activas = self._query(
            "SELECT id, device_identifier FROM workstations WHERE status='ACTIVE'")
        propias = [f for f in activas if hostname and f["device_identifier"] == hostname]
        if len(propias) == 1:
            return str(propias[0]["id"])
        if len(activas) == 1 and not activas[0]["device_identifier"]:
            return str(activas[0]["id"])
        return None

    def register(self, *, terminal_id: str, branch_id: str, hostname: str,
                 workstation_type: str, operating_system: str, app_version: str,
                 schema_version: str, protocol_version: str, now: str) -> None:
        """Crea o actualiza la fila. El estado, el nombre y el tipo de una fila
        existente no se tocan: los administra Configuración → Estaciones."""
        if self._query_one("SELECT 1 AS x FROM workstations WHERE id=?", (terminal_id,)):
            self._execute(
                "UPDATE workstations SET branch_id=?, device_identifier=?, operating_system=?,"
                " application_version=?, schema_version=?, protocol_version=?, last_seen_at=?,"
                " updated_at=? WHERE id=?",
                (branch_id, hostname, operating_system, app_version, schema_version,
                 protocol_version, now, now, terminal_id))
            return
        self._execute(
            "INSERT INTO workstations (id, branch_id, code, name, workstation_type,"
            " device_identifier, operating_system, application_version, schema_version,"
            " protocol_version, status, last_seen_at, created_at, updated_at)"
            " VALUES (?,?,?,?,?,?,?,?,?,?,'ACTIVE',?,?,?)",
            (terminal_id, branch_id, terminal_code(terminal_id), hostname or terminal_id,
             workstation_type, hostname, operating_system, app_version, schema_version,
             protocol_version, now, now, now))


__all__ = ["SqliteTerminalIdentityRepository", "TERMINAL_ID_KEY", "terminal_code"]
