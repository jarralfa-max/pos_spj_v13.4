"""The install transaction run by the EXTERNAL updater, never by the POS.

Order, with what a failure at each step leaves behind:

1. wait for the desktop process to exit, then take the database instance
   lock — failure: CANCELLED, nothing touched;
2. re-verify the staged package (size, SHA-256, Authenticode when the build
   is signed) — failure: CANCELLED;
3. verified SQLite backup of the database (`pre-update-<version>`) —
   failure: CANCELLED;
4. run the signed installer elevated (UAC) — non-zero exit: ROLLING_BACK
   without touching the database (no migration ran);
5. self-test of the NEW binaries (`--self-test`: integrity → migrations →
   schema/UUID validation) and its version must be the one announced —
   failure: ROLLING_BACK, and because migrations may have run the database
   is restored from step 3;
6. rollback = restore the database (when needed) + reinstall the previous
   version from the machine cache + self-test of the previous version →
   ROLLED_BACK; if any of that fails → NEEDS_RECOVERY, and the desktop
   blocks normal start and offers the restore.

The job is persisted at every transition, so a power cut leaves the last
reached state for the desktop to diagnose.
"""
from __future__ import annotations

from dataclasses import dataclass
import logging
from pathlib import Path
from typing import Callable, Protocol, Sequence

from backend.domain.software_distribution.update_job import UpdateJob, UpdateJobState

logger = logging.getLogger("spj.updater.transaction")


class JobStore(Protocol):
    def save(self, job: UpdateJob) -> UpdateJob: ...


class Lock(Protocol):
    def acquire(self, *, timeout_seconds: float = 0.0, poll_seconds: float = 0.25) -> bool: ...
    def release(self) -> None: ...


class BackupPort(Protocol):
    def create(self, source: Path, destination_dir: Path, *, label: str, quiescent: bool = True): ...
    def restore(self, backup_path: Path, target: Path): ...


class InstallerRunnerPort(Protocol):
    def run(self, installer: Path, arguments: Sequence[str], *, timeout_seconds: float) -> int: ...


class SelfTestPort(Protocol):
    def run(self, *, timeout_seconds: float): ...


class TrustPort(Protocol):
    def check(self, installer: Path): ...


class CachePort(Protocol):
    def installer_for(self, version: str): ...


@dataclass(frozen=True)
class TransactionTimeouts:
    app_exit_seconds: float = 180.0
    lock_seconds: float = 60.0
    installer_seconds: float = 45 * 60.0
    self_test_seconds: float = 30 * 60.0


class UpdateTransaction:
    def __init__(
        self, *, job_store: JobStore, database_lock: Lock, backup: BackupPort,
        backups_dir: Path, installer_runner: InstallerRunnerPort,
        installer_arguments: Callable[[UpdateJob, str], list[str]],
        self_test: SelfTestPort, trust: TrustPort, installer_cache: CachePort,
        verify_package: Callable[[Path, int, str], None],
        wait_for_exit: Callable[[int, float], bool],
        timeouts: TransactionTimeouts = TransactionTimeouts(),
    ) -> None:
        self._store = job_store
        self._lock = database_lock
        self._backup = backup
        self._backups_dir = Path(backups_dir)
        self._runner = installer_runner
        self._arguments = installer_arguments
        self._self_test = self_test
        self._trust = trust
        self._cache = installer_cache
        self._verify_package = verify_package
        self._wait_for_exit = wait_for_exit
        self._timeouts = timeouts

    def run(self, job: UpdateJob, *, wait_pid: int) -> UpdateJob:
        job = self._save(job.transition(UpdateJobState.WAITING_FOR_APP_EXIT,
                                        "Esperando que la aplicación se cierre."))
        if not self._wait_for_exit(wait_pid, self._timeouts.app_exit_seconds):
            return self._save(job.transition(
                UpdateJobState.CANCELLED, "La aplicación no se cerró; no se actualizó nada."))
        if not self._lock.acquire(timeout_seconds=self._timeouts.lock_seconds):
            return self._save(job.transition(
                UpdateJobState.CANCELLED,
                "Otra instancia de SPJ sigue usando la base de datos; no se actualizó nada."))
        try:
            installer = Path(job.installer_path)
            try:
                self._verify_package(installer, job.installer_size, job.installer_sha256)
                self._trust.check(installer)
            except Exception as exc:
                return self._save(job.transition(
                    UpdateJobState.CANCELLED, f"El paquete no pasó la verificación: {exc}"))

            job = self._save(job.transition(UpdateJobState.BACKING_UP,
                                            "Respaldando la base de datos."))
            database = Path(job.database_path)
            backup_path = ""
            if database.exists():
                try:
                    backup = self._backup.create(database, self._backups_dir,
                                                 label=f"pre-update-{job.to_version}")
                    backup_path = str(backup.path)
                except Exception as exc:
                    return self._save(job.transition(
                        UpdateJobState.CANCELLED,
                        f"No se pudo respaldar la base de datos; no se actualizó nada: {exc}"))

            previous = ""
            try:
                cached = self._cache.installer_for(job.from_version)
                previous = str(cached.path) if cached else ""
            except Exception as exc:  # tampered cache entry: never used
                logger.warning("Instalador previo no utilizable: %s", exc)

            job = self._save(job.transition(
                UpdateJobState.INSTALLING, f"Instalando la versión {job.to_version}.",
                backup_path=backup_path, previous_installer_path=previous))
            try:
                code = self._runner.run(installer, self._arguments(job, str(installer)),
                                        timeout_seconds=self._timeouts.installer_seconds)
            except Exception as exc:
                if not getattr(exc, "installer_started", True):
                    # UAC declined or the executable could not start: the
                    # installation was never touched.
                    return self._save(job.transition(
                        UpdateJobState.CANCELLED, f"No se instaló nada: {exc}"))
                return self._rollback(job, f"El instalador no terminó correctamente: {exc}")
            if code != 0:
                return self._rollback(job, f"El instalador terminó con código {code}.")
        finally:
            # The self-test opens the database itself and takes this lock.
            self._lock.release()

        job = self._save(job.transition(
            UpdateJobState.VERIFYING, "Probando el arranque y las migraciones.",
            migrations_may_have_run=True))
        report = self._self_test.run(timeout_seconds=self._timeouts.self_test_seconds)
        if report.ok and report.version == job.to_version:
            return self._save(job.transition(
                UpdateJobState.COMPLETED,
                f"Versión {job.to_version} instalada; esquema {report.schema_version}."))
        reason = report.detail or "La prueba de arranque falló."
        if report.ok and report.version != job.to_version:
            reason = (f"La aplicación instalada reporta la versión {report.version!r}, "
                      f"no la {job.to_version}.")
        return self._rollback(job, reason)

    # ── guided recovery (a person asked for it at startup) ────────────────
    def recover(self, job: UpdateJob) -> UpdateJob:
        """From NEEDS_RECOVERY: restore the pre-update backup, reinstall the
        previous version when its installer is cached, and self-test. Ends
        RECOVERED when the application starts again; otherwise the job stays
        NEEDS_RECOVERY with the attempt written in its history."""
        if job.state is not UpdateJobState.NEEDS_RECOVERY:
            raise ValueError(f"La actualización {job.job_id} no requiere recuperación.")
        problems: list[str] = []
        if job.backup_path:
            if not self._lock.acquire(timeout_seconds=self._timeouts.lock_seconds):
                problems.append("La base está abierta por otra instancia.")
            else:
                try:
                    self._backup.restore(Path(job.backup_path), Path(job.database_path))
                except Exception as exc:
                    problems.append(f"No se pudo restaurar la base: {exc}")
                finally:
                    self._lock.release()
        if not problems and job.previous_installer_path:
            previous = Path(job.previous_installer_path)
            try:
                self._trust.check(previous)
                code = self._runner.run(previous, self._arguments(job, str(previous)),
                                        timeout_seconds=self._timeouts.installer_seconds)
                if code != 0:
                    problems.append(f"El instalador de la versión {job.from_version} "
                                    f"terminó con código {code}.")
            except Exception as exc:
                problems.append(f"No se pudo reinstalar la versión {job.from_version}: {exc}")
        if not problems:
            report = self._self_test.run(timeout_seconds=self._timeouts.self_test_seconds)
            if report.ok:
                return self._save(job.transition(
                    UpdateJobState.RECOVERED,
                    f"Recuperación terminada: arranca la versión {report.version}"
                    + (" con la base restaurada." if job.backup_path else ".")))
            problems.append(report.detail or "La aplicación sigue sin arrancar.")
        return self._save(job.annotate("Recuperación incompleta: " + " ".join(problems)))

    # ── rollback ──────────────────────────────────────────────────────────
    def _rollback(self, job: UpdateJob, reason: str) -> UpdateJob:
        job = self._save(job.transition(UpdateJobState.ROLLING_BACK, f"Revirtiendo: {reason}"))
        problems: list[str] = []

        if job.migrations_may_have_run:
            if not job.backup_path:
                problems.append("No hay respaldo previo para restaurar la base.")
            elif not self._lock.acquire(timeout_seconds=self._timeouts.lock_seconds):
                problems.append("No se pudo bloquear la base para restaurarla.")
            else:
                try:
                    self._backup.restore(Path(job.backup_path), Path(job.database_path))
                except Exception as exc:
                    problems.append(f"No se pudo restaurar la base: {exc}")
                finally:
                    self._lock.release()

        if job.previous_installer_path:
            previous = Path(job.previous_installer_path)
            try:
                self._trust.check(previous)
                code = self._runner.run(previous, self._arguments(job, str(previous)),
                                        timeout_seconds=self._timeouts.installer_seconds)
                if code != 0:
                    problems.append(f"El instalador de la versión {job.from_version} "
                                    f"terminó con código {code}.")
            except Exception as exc:
                problems.append(f"No se pudo reinstalar la versión {job.from_version}: {exc}")

        if not problems:
            report = self._self_test.run(timeout_seconds=self._timeouts.self_test_seconds)
            if not (report.ok and report.version == job.from_version):
                problems.append(
                    f"La versión {job.from_version} no arrancó tras revertir "
                    f"({report.detail or report.version or 'sin detalle'}).")
                if not job.previous_installer_path:
                    problems.append(f"No hay instalador guardado de la versión {job.from_version}.")

        if problems:
            return self._save(job.transition(
                UpdateJobState.NEEDS_RECOVERY,
                f"{reason} La reversión automática no terminó: " + " ".join(problems)))
        return self._save(job.transition(
            UpdateJobState.ROLLED_BACK,
            f"{reason} Se volvió a la versión {job.from_version}"
            + (" y se restauró la base de datos." if job.migrations_may_have_run else ".")))

    def _save(self, job: UpdateJob) -> UpdateJob:
        logger.info("Actualización %s: %s — %s", job.job_id, job.state.value, job.last_detail)
        return self._store.save(job)
