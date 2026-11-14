"""PreMigrationBackupStep — ninguna migración sin respaldo verificado.

El actualizador externo respalda antes de instalar, pero el Setup manual y el
atajo «Reparar» no pasan por él: las migraciones corren en el siguiente arranque.
Este paso cubre todos los caminos con el mismo `SQLiteBackupService`.

Sólo respalda cuando hay datos y migraciones pendientes: sin pendientes `up()` no
toca nada, y una base recién creada no tiene nada que perder. Si el respaldo
falla el arranque se detiene ANTES de migrar.

Tras una actualización por el actualizador este paso repite el respaldo durante
la autoprueba: el costo es disco, y a cambio ningún camino queda exento.

Corre después de `SchemaCompatibilityStep` (una base más nueva que el binario no
se migra) y antes de `DatabaseMigrationStep`. Quien lo ejecuta tiene el candado
de instancia, por eso la copia se verifica también fila por fila.
"""
from __future__ import annotations

from pathlib import Path

from backend.bootstrap.bootstrap_context import BootstrapContext
from backend.bootstrap.bootstrap_severity import BootstrapFailureReason
from backend.bootstrap.bootstrap_state import BootstrapState
from backend.bootstrap.bootstrap_step_result import BootstrapStepResult
from backend.bootstrap.steps.schema_compatibility_step import known_migration_versions
from backend.infrastructure.db.sqlite_backup import SQLiteBackupService
from backend.shared.app_version import VERSION


def _pending_versions(connection) -> frozenset[str]:
    tracked = connection.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='schema_migrations'"
    ).fetchone()
    if tracked is None:
        return known_migration_versions()
    applied = {str(row[0]) for row in connection.execute("SELECT version FROM schema_migrations")}
    return known_migration_versions() - applied


def _has_tables(connection) -> bool:
    return connection.execute("SELECT 1 FROM sqlite_master WHERE type='table' LIMIT 1"
                              ).fetchone() is not None


def _backups_dir(context: BootstrapContext) -> Path:
    if context.backups_dir is not None:
        return Path(context.backups_dir)
    if context.app_paths is not None:
        return context.app_paths.backups_dir
    return context.db_path.parent / "backups"


class PreMigrationBackupStep:
    name = "pre_migration_backup"
    resulting_state = BootstrapState.DATABASE_CHECKING

    def run(self, context: BootstrapContext) -> BootstrapStepResult:
        if context.conn is None:
            return BootstrapStepResult.fatal(
                self.name, BootstrapFailureReason.BOOTSTRAP_INVALID,
                "pre_migration_backup ejecutado sin conexión (database_integrity va antes).")
        pending = _pending_versions(context.conn)
        if not pending:
            return BootstrapStepResult.ok(self.name, "Sin migraciones pendientes.")
        if not _has_tables(context.conn):
            return BootstrapStepResult.ok(self.name, "Base nueva: no hay datos que respaldar.")

        destination = _backups_dir(context)
        try:
            backup = SQLiteBackupService(app_version=VERSION).create(
                context.db_path, destination, label=f"pre-migration-{VERSION}")
        except Exception as exc:  # disco lleno, permisos, verificación fallida
            return BootstrapStepResult.fatal(
                self.name, BootstrapFailureReason.PRE_MIGRATION_BACKUP_FAILED,
                f"No se pudo respaldar la base de datos en {destination}: {exc}. "
                f"No se migró nada: hay {len(pending)} migraciones pendientes y la base sigue "
                "como estaba. Libere espacio o corrija los permisos de esa carpeta y vuelva a "
                "abrir SPJ.", exception=exc)
        context.pre_migration_backup = backup.path
        return BootstrapStepResult.ok(self.name, f"Base respaldada en {backup.path}.")
