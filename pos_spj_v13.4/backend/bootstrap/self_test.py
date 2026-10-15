"""`SPJ.exe --self-test --json` — headless start check, no window.

Used by the external updater right after installing (and after a rollback)
and by the Windows CI job on a machine without Python. It runs EXACTLY the
desktop's own start path up to the login, minus Qt:

    install_config.json → AppPaths → legacy relocation → instance lock →
    integrity → schema compatibility → migrations → schema/UUID validation

and prints one JSON line:

    {"ok": true, "version": "13.5.0", "schema_version": 339,
     "database": "...", "layout": "installed", "detail": "..."}

Exit code 0 only when `ok` is true.
"""
from __future__ import annotations

import json
import logging
import sys

from backend.shared.app_version import VERSION


def run_self_test(paths=None) -> dict:
    report: dict = {"ok": False, "version": VERSION, "schema_version": None,
                    "database": "", "layout": "", "detail": ""}
    try:
        from backend.shared.app_paths import AppPaths
        from backend.shared.install_config import InstallConfigError

        try:
            paths = paths or AppPaths.from_environment()
        except InstallConfigError as exc:
            report["detail"] = str(exc)
            return report
        report["database"] = str(paths.database_path)
        report["layout"] = paths.effective_layout

        from backend.infrastructure.db.database_relocation import LegacyDatabaseRelocator
        from backend.infrastructure.runtime.instance_lock import InstanceLock

        relocation = LegacyDatabaseRelocator(paths).run()
        if relocation.blocks_startup:
            report["detail"] = relocation.message
            return report

        lock = InstanceLock(paths.instance_lock_path)
        if not lock.acquire(timeout_seconds=30):
            report["detail"] = "La base de datos está abierta por otra instancia."
            return report
        try:
            from backend.bootstrap.run_database_bootstrap import run_database_bootstrap_sequence
            from backend.infrastructure.db.sqlite_backup import database_schema_version

            paths.database_dir.mkdir(parents=True, exist_ok=True)
            result = run_database_bootstrap_sequence(paths.database_path)
            connection = result.context.conn
            try:
                if not result.success:
                    failed = result.failed_step()
                    report["detail"] = (failed.message if failed
                                        else "Fallo desconocido al preparar la base de datos.")
                    return report
                if connection is not None:
                    report["schema_version"] = database_schema_version(connection)
            finally:
                if connection is not None:
                    connection.close()
        finally:
            lock.release()
        report["ok"] = True
        report["detail"] = (f"Base lista ({result.final_state.value}); "
                            f"reubicación: {relocation.status.value}.")
        return report
    except Exception as exc:  # the probe must always answer with JSON
        logging.getLogger("spj.self_test").exception("Autoprueba fallida")
        report["detail"] = f"{type(exc).__name__}: {exc}"
        return report


def main(argv: list[str] | None = None) -> int:
    """`--report <file>` also writes the JSON there: a windowed executable
    (PyInstaller `console=False`) may have no usable stdout."""
    argv = list(sys.argv if argv is None else argv)
    report_file = None
    if "--report" in argv:
        index = argv.index("--report")
        report_file = argv[index + 1] if index + 1 < len(argv) else None
    if sys.stderr is not None:
        logging.basicConfig(level=logging.WARNING, stream=sys.stderr)
    report = run_self_test()
    line = json.dumps(report, ensure_ascii=False)
    if report_file:
        with open(report_file, "w", encoding="utf-8") as handle:
            handle.write(line + "\n")
    if sys.stdout is not None:
        sys.stdout.write(line + "\n")
        sys.stdout.flush()
    return 0 if report["ok"] else 1
