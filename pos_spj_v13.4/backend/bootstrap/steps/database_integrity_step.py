"""DatabaseIntegrityStep — SHELL-3.

Opens the single connection every later step reuses (`context.conn`) and
checks it isn't corrupted before anything tries to migrate or read it. A
brand-new, empty database file is not a corruption finding — only a
non-empty database that fails `PRAGMA integrity_check` is fatal
(§9: "base de datos dañada sin recuperación").
"""
from __future__ import annotations

import sqlite3

from backend.bootstrap.bootstrap_context import BootstrapContext
from backend.bootstrap.bootstrap_severity import BootstrapFailureReason
from backend.bootstrap.bootstrap_state import BootstrapState
from backend.bootstrap.bootstrap_step_result import BootstrapStepResult


class DatabaseIntegrityStep:
    name = "database_integrity"
    resulting_state = BootstrapState.DATABASE_CHECKING

    def run(self, context: BootstrapContext) -> BootstrapStepResult:
        context.db_path.parent.mkdir(parents=True, exist_ok=True)
        is_new = not context.db_path.exists()

        try:
            conn = sqlite3.connect(str(context.db_path))
            conn.row_factory = sqlite3.Row
        except sqlite3.Error as exc:
            return BootstrapStepResult.fatal(
                self.name, BootstrapFailureReason.DATABASE_CORRUPTED_UNRECOVERABLE,
                f"No se pudo abrir la base de datos en {context.db_path}: {exc}",
                exception=exc,
            )

        if is_new:
            context.conn = conn
            return BootstrapStepResult.ok(self.name, f"Base de datos nueva en {context.db_path}.")

        try:
            row = conn.execute("PRAGMA integrity_check").fetchone()
        except sqlite3.Error as exc:
            conn.close()
            return BootstrapStepResult.fatal(
                self.name, BootstrapFailureReason.DATABASE_CORRUPTED_UNRECOVERABLE,
                f"PRAGMA integrity_check falló: {exc}", exception=exc,
            )

        result = str(row[0]) if row else "unknown"
        if result.lower() != "ok":
            conn.close()
            return BootstrapStepResult.fatal(
                self.name, BootstrapFailureReason.DATABASE_CORRUPTED_UNRECOVERABLE,
                f"La base de datos está dañada: {result}",
            )

        context.conn = conn
        return BootstrapStepResult.ok(self.name, "Integridad de la base de datos verificada.")
