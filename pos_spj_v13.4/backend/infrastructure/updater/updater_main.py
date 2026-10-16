"""`spj_updater.exe` — the external updater process.

Started by the desktop (`update_launcher.py`) from a temporary copy, AFTER the
desktop has written the job and while it is closing. Never imports Qt or the
ERP: only the job journal, the SQLite backup, the instance lock, the package
check and process control. Modes:

* ``install`` — run `UpdateTransaction.run` for the staged job;
* ``recover`` — run `UpdateTransaction.recover` for a NEEDS_RECOVERY job
  (a person chose it in the desktop's recovery dialog).

When it finishes it starts the desktop again (also after a failure: the
desktop is what explains the result and offers recovery).

    spj_updater.exe --mode install --job <update_job.json> --wait-pid <pid>
                    --install-dir <dir> --data-dir <dir> --installer-cache <dir>
                    [--require-signature]
"""
from __future__ import annotations

import argparse
import logging
from pathlib import Path
import sys
import threading

if __package__ in (None, ""):
    # Frozen single-file build: the package root is bundled at the top level.
    sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from backend.application.software_updates.update_transaction import UpdateTransaction  # noqa: E402
from backend.domain.software_distribution.update_job import UpdateJob, UpdateJobState  # noqa: E402
from backend.infrastructure.db.sqlite_backup import SQLiteBackupService  # noqa: E402
from backend.infrastructure.runtime.instance_lock import InstanceLock  # noqa: E402
from backend.infrastructure.updater.installer_trust import (  # noqa: E402
    AuthenticodeVerifier,
    InstallerCache,
)
from backend.infrastructure.updater.package_integrity import verify_file  # noqa: E402
from backend.infrastructure.updater.process_control import (  # noqa: E402
    InstallerRunner,
    SelfTestProbe,
    inno_silent_arguments,
    launch_detached,
    wait_for_process_exit,
)
from backend.infrastructure.updater.update_job_store import UpdateJobStore  # noqa: E402
from backend.shared.app_paths import AppPaths  # noqa: E402

logger = logging.getLogger("spj.updater")

EXIT_OK = 0
EXIT_FAILED = 1
EXIT_BUSY = 2


def parse_arguments(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="spj_updater")
    parser.add_argument("--mode", choices=("install", "recover"), default="install")
    parser.add_argument("--job", required=True, type=Path)
    parser.add_argument("--wait-pid", type=int, default=0)
    parser.add_argument("--install-dir", required=True, type=Path)
    parser.add_argument("--data-dir", type=Path)
    parser.add_argument("--installer-cache", type=Path)
    parser.add_argument("--require-signature", action="store_true")
    parser.add_argument("--no-relaunch", action="store_true")
    parser.add_argument("--headless", action="store_true")
    return parser.parse_args(argv)


def app_command(paths: AppPaths) -> list[str]:
    if paths.is_installed:
        return [str(paths.root / "SPJ.exe")]
    return [sys.executable, str(paths.root / "main.py")]


def build_transaction(paths: AppPaths, job: UpdateJob, *, store: UpdateJobStore,
                      require_signature: bool) -> UpdateTransaction:
    database = Path(job.database_path)
    logs = paths.logs_dir
    logs.mkdir(parents=True, exist_ok=True)

    per_user = paths.install_config is not None and paths.install_config.install_mode == "user"

    def arguments(current: UpdateJob, installer: str) -> list[str]:
        name = Path(installer).stem
        extra = ["/CURRENTUSER"] if per_user else []
        return [*inno_silent_arguments(logs / f"instalador-{current.job_id}-{name}.log"), *extra]

    return UpdateTransaction(
        job_store=store,
        database_lock=InstanceLock(database.with_name(database.name + ".lock")),
        backup=SQLiteBackupService(app_version=job.from_version),
        backups_dir=paths.backups_dir,
        installer_runner=InstallerRunner(elevate=not per_user),
        installer_arguments=arguments,
        self_test=SelfTestProbe(app_command(paths)),
        trust=AuthenticodeVerifier(required=require_signature),
        installer_cache=InstallerCache(paths.installer_cache_dir),
        verify_package=verify_file,
        wait_for_exit=lambda pid, timeout: wait_for_process_exit(pid, timeout_seconds=timeout),
    )


def run(args: argparse.Namespace) -> int:
    paths = AppPaths.for_installation(args.install_dir, data_dir=args.data_dir,
                                      installer_cache=args.installer_cache)
    paths.logs_dir.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        filename=str(paths.logs_dir / "updater.log"), level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s", encoding="utf-8")

    updater_lock = InstanceLock(paths.updater_lock_path)
    if not updater_lock.acquire():
        logger.error("Ya hay un actualizador en ejecución.")
        return EXIT_BUSY
    try:
        store = UpdateJobStore(args.job)
        job = store.load()
        if job is None:
            logger.error("No existe el trabajo de actualización %s", args.job)
            return EXIT_FAILED
        transaction = build_transaction(paths, job, store=store,
                                        require_signature=args.require_signature)
        status = _StatusWindow.create(enabled=not args.headless, job=job, store=store)
        outcome: dict[str, UpdateJob] = {}

        def work() -> None:
            try:
                if args.mode == "recover":
                    outcome["job"] = transaction.recover(job)
                elif job.state is UpdateJobState.STAGED:
                    outcome["job"] = transaction.run(job, wait_pid=args.wait_pid)
                else:
                    logger.error("El trabajo %s no está preparado (%s).", job.job_id, job.state)
                    outcome["job"] = job
            except Exception:
                logger.exception("Fallo inesperado del actualizador")
                outcome["job"] = store.load() or job
            finally:
                status.finish()

        worker = threading.Thread(target=work, name="spj-update", daemon=False)
        worker.start()
        status.loop()
        worker.join()
        final = outcome.get("job", job)
        logger.info("Resultado: %s — %s", final.state.value, final.last_detail)
        succeeded = final.state in {UpdateJobState.COMPLETED, UpdateJobState.RECOVERED}
    finally:
        updater_lock.release()

    if not args.no_relaunch:
        try:
            launch_detached(app_command(paths), working_directory=paths.root)
        except OSError:
            logger.exception("No se pudo volver a abrir SPJ")
    return EXIT_OK if succeeded else EXIT_FAILED


class _StatusWindow:
    """Small always-on-top window so the person at the till sees that an
    update is running. Tkinter only; headless when unavailable."""

    def __init__(self, root, job: UpdateJob, store: UpdateJobStore) -> None:
        self._root = root
        self._store = store
        self._done = threading.Event()
        import tkinter as tk

        root.title("Actualizando SPJ")
        root.attributes("-topmost", True)
        root.resizable(False, False)
        root.protocol("WM_DELETE_WINDOW", lambda: None)  # cannot be closed mid-update
        tk.Label(root, text=f"Actualizando SPJ a la versión {job.to_version}",
                 font=("Segoe UI", 12, "bold"), padx=24, pady=12).pack()
        self._label = tk.Label(root, text=job.state.label, font=("Segoe UI", 10),
                               padx=24, pady=8, wraplength=420, justify="left")
        self._label.pack()
        tk.Label(root, text="No apague el equipo. SPJ se abrirá al terminar.",
                 font=("Segoe UI", 9), padx=24, pady=12).pack()
        self._poll()

    @classmethod
    def create(cls, *, enabled: bool, job: UpdateJob, store: UpdateJobStore):
        if not enabled:
            return _Headless()
        try:
            import tkinter as tk

            return cls(tk.Tk(), job, store)
        except Exception:
            return _Headless()

    def _poll(self) -> None:
        try:
            job = self._store.load()
            if job is not None:
                self._label.configure(text=f"{job.state.label}. {job.last_detail}")
        except Exception:
            pass
        if self._done.is_set():
            self._root.destroy()
            return
        self._root.after(700, self._poll)

    def finish(self) -> None:
        self._done.set()

    def loop(self) -> None:
        self._root.mainloop()


class _Headless:
    def __init__(self) -> None:
        self._done = threading.Event()

    def finish(self) -> None:
        self._done.set()

    def loop(self) -> None:
        self._done.wait()


def main(argv: list[str] | None = None) -> int:
    return run(parse_arguments(argv))


if __name__ == "__main__":
    sys.exit(main())
