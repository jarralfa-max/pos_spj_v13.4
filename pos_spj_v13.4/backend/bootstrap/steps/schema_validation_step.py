"""SchemaValidationStep — SHELL-3/SHELL-4.

Three different bars, deliberately:

- The security/identity-critical tables (`usuarios`, `sucursales`,
  `configuraciones`, `roles`, `rol_permisos`, `installation`) are a hard
  FATAL gate — nothing in SHELL-1/2 works without them.
- UUIDv7 identity is validated two ways, both FATAL: the installation's own
  sentinel constants (`INSTALL_BRANCH_UUID` etc.) must themselves be
  well-formed UUIDv7 — a cheap, code-level sanity check — and, the
  authoritative check, `assert_uuid_identity()` (SHELL-4 — previously called
  ad hoc from `main.py`'s third, now-removed migration block) scans every
  table in the database for a leftover `INTEGER PRIMARY KEY`. This is the
  single place that check runs now; it is not duplicated elsewhere.
- Broader table coverage (`scripts/verify_tables.py`'s full critical list,
  which includes legacy tables like `detalle_ventas`/`empleados` — known
  pre-existing gaps on this branch per the SHELL-0 audit) is only a
  WARNING. Treating that list as FATAL would block every boot today for
  gaps unrelated to security/identity; that cleanup is separate,
  pre-existing debt, not something this step should block startup over.
"""
from __future__ import annotations

from backend.bootstrap.bootstrap_context import BootstrapContext
from backend.bootstrap.bootstrap_severity import BootstrapFailureReason
from backend.bootstrap.bootstrap_state import BootstrapState
from backend.bootstrap.bootstrap_step_result import BootstrapStepResult
from backend.infrastructure.db.uuid_cutover import IntegerIdentityError, assert_uuid_identity
from backend.shared.ids import (
    INSTALL_BRANCH_UUID,
    INSTALL_CASHBOX_UUID,
    INSTALLATION_SINGLETON_UUID,
    SYSTEM_ROLE_UUIDS,
    is_uuidv7,
)

_CRITICAL_TABLES = ("usuarios", "sucursales", "configuraciones", "roles", "rol_permisos", "installation")


class SchemaValidationStep:
    name = "schema_validation"
    resulting_state = BootstrapState.SCHEMA_VALIDATED

    def run(self, context: BootstrapContext) -> BootstrapStepResult:
        if context.conn is None:
            return BootstrapStepResult.fatal(
                self.name, BootstrapFailureReason.BOOTSTRAP_INVALID,
                "schema_validation ejecutado sin una conexión abierta.",
            )

        existing = {
            row[0] for row in context.conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
        missing_critical = [t for t in _CRITICAL_TABLES if t not in existing]
        if missing_critical:
            return BootstrapStepResult.fatal(
                self.name, BootstrapFailureReason.SCHEMA_INCOMPLETE,
                f"Tablas críticas ausentes tras la migración: {', '.join(missing_critical)}",
            )

        identity_constants = {
            "INSTALL_BRANCH_UUID": INSTALL_BRANCH_UUID,
            "INSTALL_CASHBOX_UUID": INSTALL_CASHBOX_UUID,
            "INSTALLATION_SINGLETON_UUID": INSTALLATION_SINGLETON_UUID,
            **{f"SYSTEM_ROLE_UUIDS[{k}]": v for k, v in SYSTEM_ROLE_UUIDS.items()},
        }
        invalid = [name for name, value in identity_constants.items() if not is_uuidv7(value)]
        if invalid:
            return BootstrapStepResult.fatal(
                self.name, BootstrapFailureReason.IDENTITY_NOT_UUIDV7,
                f"Identidades de instalación no son UUIDv7 canónico: {', '.join(invalid)}",
            )

        try:
            assert_uuid_identity(context.conn)
        except IntegerIdentityError as exc:
            return BootstrapStepResult.fatal(
                self.name, BootstrapFailureReason.IDENTITY_NOT_UUIDV7, str(exc), exception=exc,
            )

        coverage_warning = self._check_broad_coverage(context)
        if coverage_warning is not None:
            return coverage_warning

        return BootstrapStepResult.ok(self.name, "Esquema e identidad UUIDv7 validados.")

    def _check_broad_coverage(self, context: BootstrapContext) -> BootstrapStepResult | None:
        try:
            from scripts.verify_tables import verificar_tablas

            resultado = verificar_tablas(str(context.db_path))
        except Exception:
            return None  # informational only — never fail the boot over this check itself

        faltantes = resultado.get("faltantes") or []
        if not faltantes:
            return None
        return BootstrapStepResult.warning(
            self.name, BootstrapFailureReason.SCHEMA_COVERAGE_INCOMPLETE,
            f"Cobertura de tablas críticas (no relacionadas a identidad/seguridad) "
            f"incompleta: {', '.join(faltantes)} ({resultado.get('cobertura_pct')}%).",
        )
