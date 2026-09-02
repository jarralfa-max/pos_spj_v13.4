"""Concrete HealthCheck implementations — SHELL-3 §69.

Only checks backed by infrastructure that already exists today: database,
schema, UUID identity, secret store, disk space, clock. Module registry,
route registry, event subscriptions, background workers, and critical
devices belong to later phases (SHELL-8, SHELL-9, SHELL-14) — adding stub
checks for subsystems that don't exist yet would just report a permanent,
meaningless UNKNOWN, so they're left out until there's something real to
check.
"""
from __future__ import annotations

import shutil
from datetime import datetime, timezone

from backend.bootstrap.bootstrap_context import BootstrapContext
from backend.bootstrap.health.health_status import HealthCheckResult, HealthStatus
from backend.security.secrets.errors import SecretStoreUnavailableError
from backend.shared.ids import INSTALL_BRANCH_UUID, INSTALL_CASHBOX_UUID, INSTALLATION_SINGLETON_UUID
from backend.shared.ids import SYSTEM_ROLE_UUIDS, is_uuidv7

_CRITICAL_TABLES = ("usuarios", "sucursales", "configuraciones", "roles", "rol_permisos", "installation")

# UUIDv7 embeds a millisecond timestamp; a clock further back than this
# predates the whole SPJ v13 UUIDv7 cutover and would corrupt lexicographic
# ordering guarantees relied on elsewhere (see backend/shared/ids.py).
_MINIMUM_SANE_CLOCK = datetime(2024, 1, 1, tzinfo=timezone.utc)

_MINIMUM_FREE_DISK_BYTES = 500 * 1024 * 1024  # 500 MiB


class DatabaseHealthCheck:
    name = "database"

    def check(self, context: BootstrapContext) -> HealthCheckResult:
        if context.conn is None:
            return HealthCheckResult(self.name, HealthStatus.UNKNOWN, "No hay conexión de base de datos activa.")
        try:
            row = context.conn.execute("PRAGMA integrity_check").fetchone()
            result = str(row[0]) if row else "unknown"
        except Exception as exc:
            return HealthCheckResult(self.name, HealthStatus.UNHEALTHY, f"integrity_check falló: {exc}")
        if result.lower() == "ok":
            return HealthCheckResult(self.name, HealthStatus.HEALTHY, "Integridad verificada (PRAGMA integrity_check).")
        return HealthCheckResult(self.name, HealthStatus.UNHEALTHY, f"integrity_check reportó: {result}")


class SchemaHealthCheck:
    name = "schema"

    def check(self, context: BootstrapContext) -> HealthCheckResult:
        if context.conn is None:
            return HealthCheckResult(self.name, HealthStatus.UNKNOWN, "No hay conexión de base de datos activa.")
        existing = {
            row[0] for row in context.conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
        missing = [t for t in _CRITICAL_TABLES if t not in existing]
        if missing:
            return HealthCheckResult(
                self.name, HealthStatus.UNHEALTHY, f"Tablas críticas ausentes: {', '.join(missing)}",
            )
        return HealthCheckResult(self.name, HealthStatus.HEALTHY, "Tablas críticas presentes.")


class UuidIdentityHealthCheck:
    name = "uuid_identity"

    def check(self, context: BootstrapContext) -> HealthCheckResult:
        constants = {
            "INSTALL_BRANCH_UUID": INSTALL_BRANCH_UUID,
            "INSTALL_CASHBOX_UUID": INSTALL_CASHBOX_UUID,
            "INSTALLATION_SINGLETON_UUID": INSTALLATION_SINGLETON_UUID,
            **{f"SYSTEM_ROLE_UUIDS[{k}]": v for k, v in SYSTEM_ROLE_UUIDS.items()},
        }
        invalid = [name for name, value in constants.items() if not is_uuidv7(value)]
        if invalid:
            return HealthCheckResult(
                self.name, HealthStatus.UNHEALTHY,
                f"Identidades de instalación no-UUIDv7: {', '.join(invalid)}",
            )

        if context.conn is not None:
            try:
                rows = context.conn.execute("SELECT id FROM usuarios").fetchall()
                bad = [r[0] for r in rows if not is_uuidv7(r[0])]
            except Exception:
                bad = []
            if bad:
                return HealthCheckResult(
                    self.name, HealthStatus.UNHEALTHY,
                    f"{len(bad)} usuario(s) con id no-UUIDv7 (posible DB legacy).",
                )
        return HealthCheckResult(self.name, HealthStatus.HEALTHY, "Identidad UUIDv7 verificada.")


class SecretStoreHealthCheck:
    name = "secret_store"

    def check(self, context: BootstrapContext) -> HealthCheckResult:
        from backend.security.secrets.encrypted_local_secret_store import EncryptedLocalSecretStore

        try:
            EncryptedLocalSecretStore(app_paths=context.app_paths)
        except SecretStoreUnavailableError as exc:
            return HealthCheckResult(self.name, HealthStatus.DEGRADED, f"Almacén de secretos no disponible: {exc}")
        except Exception as exc:
            return HealthCheckResult(self.name, HealthStatus.UNHEALTHY, f"Almacén de secretos falló: {exc}")
        return HealthCheckResult(self.name, HealthStatus.HEALTHY, "Almacén de secretos local accesible.")


class DiskSpaceHealthCheck:
    name = "disk_space"

    def check(self, context: BootstrapContext) -> HealthCheckResult:
        if context.app_paths is None:
            return HealthCheckResult(self.name, HealthStatus.UNKNOWN, "AppPaths no resuelto todavía.")
        try:
            usage = shutil.disk_usage(context.app_paths.user_data_dir)
        except OSError as exc:
            return HealthCheckResult(self.name, HealthStatus.UNKNOWN, f"No se pudo consultar espacio en disco: {exc}")
        if usage.free < _MINIMUM_FREE_DISK_BYTES:
            free_mb = usage.free // (1024 * 1024)
            return HealthCheckResult(
                self.name, HealthStatus.DEGRADED, f"Espacio libre bajo: {free_mb} MiB.",
            )
        return HealthCheckResult(self.name, HealthStatus.HEALTHY, "Espacio en disco suficiente.")


class ClockHealthCheck:
    name = "clock"

    def check(self, context: BootstrapContext) -> HealthCheckResult:
        now = datetime.now(timezone.utc)
        if now < _MINIMUM_SANE_CLOCK:
            return HealthCheckResult(
                self.name, HealthStatus.UNHEALTHY,
                f"Reloj del sistema inválido ({now.isoformat()}) — compromete el orden de UUIDv7.",
            )
        return HealthCheckResult(self.name, HealthStatus.HEALTHY, "Reloj del sistema es razonable.")


def default_health_checks() -> list:
    return [
        DatabaseHealthCheck(), SchemaHealthCheck(), UuidIdentityHealthCheck(),
        SecretStoreHealthCheck(), DiskSpaceHealthCheck(), ClockHealthCheck(),
    ]
