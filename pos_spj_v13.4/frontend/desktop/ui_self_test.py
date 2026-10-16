"""`SPJ.exe --self-test-ui --report <file.json> [--screenshots <dir>]` — the
start check WITH windows.

`--self-test` proves paths, relocation and migrations without Qt. This one
proves what an installed bundle needs to actually be used: the Qt platform
plugin, styles and fonts, the official artwork, the login window, the main
window and EVERY module route the station's profile enables, and QtWebEngine
(charts) — the things that break in a PyInstaller bundle when a plugin, DLL or
data file is missing.

Safety: it never authenticates anyone and never accepts input. The windows
run against a TEMPORARY COPY of the database (SQLite backup API), deleted at
the end: opening some routes writes (the POS starts a draft sale), and the
station's real database must not change because of a self-test. The main
window is composed with a synthetic administrator context (fresh UUIDv7 ids)
ONLY to render the routes, its background services are stopped before the
first event is processed (no outbox is drained, no WhatsApp message is sent),
and the process exits. An exception raised inside a Qt slot is recorded in the
report instead of aborting the process (PyQt5 aborts when `sys.excepthook` is
the default one; the real desktop installs its own crash handler).

Failure classes:
* `packaging` — ImportError/ModuleNotFoundError/FileNotFoundError/OSError, a
  missing WebEngine, or a window that cannot be built: the bundle is broken →
  exit code 1;
* `route_warnings` — any other exception while opening a route with a
  synthetic context on this database: reported, not fatal.
"""
from __future__ import annotations

import json
import logging
import os
from pathlib import Path
import sys
import time
import traceback

logger = logging.getLogger("SPJ.UiSelfTest")

_PACKAGING_ERRORS = (ImportError, ModuleNotFoundError, FileNotFoundError, OSError)


def _argument(argv: list[str], name: str) -> str | None:
    if name in argv:
        index = argv.index(name)
        return argv[index + 1] if index + 1 < len(argv) else None
    return None


def _write(report: dict, report_file: str | None) -> None:
    line = json.dumps(report, ensure_ascii=False)
    if report_file:
        Path(report_file).write_text(line + "\n", encoding="utf-8")
    if sys.stdout is not None:
        sys.stdout.write(line + "\n")
        sys.stdout.flush()


def _pump(app, seconds: float) -> None:
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        app.processEvents()
        time.sleep(0.02)


def _grab(widget, directory: Path | None, name: str, report: dict) -> None:
    if directory is None:
        return
    directory.mkdir(parents=True, exist_ok=True)
    target = directory / f"{name}.png"
    if widget.grab().save(str(target)):
        report["screenshots"].append(str(target))


def _check_webengine(app, report: dict) -> None:
    try:
        from PyQt5.QtWebEngineWidgets import QWebEngineView
    except ImportError as exc:
        report["webengine"] = f"ausente: {exc}"
        report["packaging"].append(f"QtWebEngine no está en el paquete: {exc}")
        return
    # The FIRST start of a freshly installed QtWebEngineProcess.exe can be slow
    # (antivirus scan, cold disk): 60 s and one retry before calling it broken.
    started = time.monotonic()
    for attempt in (1, 2):
        view = QWebEngineView()
        loaded: dict[str, bool] = {}
        view.loadFinished.connect(lambda ok, box=loaded: box.setdefault("ok", ok))
        view.setHtml("<html><body><p id='spj'>ok</p></body></html>")
        deadline = time.monotonic() + 60
        while "ok" not in loaded and time.monotonic() < deadline:
            app.processEvents()
            time.sleep(0.05)
        view.deleteLater()
        if loaded.get("ok"):
            report["webengine"] = "ok"
            report["webengine_seconds"] = round(time.monotonic() - started, 1)
            report["webengine_attempts"] = attempt
            return
    report["webengine"] = "sin respuesta"
    report["webengine_seconds"] = round(time.monotonic() - started, 1)
    report["packaging"].append(
        "QtWebEngine no cargó una página en 2 intentos (¿falta QtWebEngineProcess.exe o sus "
        "recursos?).")


def run_ui_self_test(argv: list[str]) -> int:
    from backend.bootstrap.self_test import run_self_test

    report_file = _argument(argv, "--report")
    shots = _argument(argv, "--screenshots")
    screenshots = Path(shots) if shots else None
    report = run_self_test()
    report.update({"ui": False, "packaging": [], "route_warnings": [], "routes": [],
                   "screenshots": [], "webengine": "", "login_window": False,
                   "main_window": False})
    if not report["ok"]:
        _write(report, report_file)
        return 1
    report["ok"] = False

    connection = None
    lock = None
    workdir = None
    slot_errors: list[str] = []

    def _slot_hook(kind, value, tb):
        slot_errors.append(f"{kind.__name__}: {value}")
        if issubclass(kind, _PACKAGING_ERRORS):
            report["packaging"].append(f"excepción en la interfaz: {kind.__name__}: {value}")

    previous_hook = sys.excepthook
    sys.excepthook = _slot_hook
    try:
        from PyQt5.QtCore import Qt
        from PyQt5.QtWidgets import QApplication

        from backend.shared.app_version import APP_NAME, VERSION

        QApplication.setAttribute(Qt.AA_ShareOpenGLContexts)
        app = QApplication.instance() or QApplication(sys.argv[:1])
        app.setApplicationName(APP_NAME)
        app.setApplicationVersion(VERSION)
        report["qt_platform"] = app.platformName()

        from frontend.desktop.components.branding import BrandAssetProvider

        BrandAssetProvider.apply_to_application(app)
        report["app_icon"] = not app.windowIcon().isNull()
        try:
            from frontend.desktop.themes.theme_manager import ThemeManager

            ThemeManager.instance().restore(app)
        except Exception as exc:  # the real start also tolerates this
            report["route_warnings"].append(f"tema: {exc}")

        from backend.bootstrap.run_database_bootstrap import run_database_bootstrap_sequence
        from backend.infrastructure.db.connection import set_db_path
        from backend.shared.app_paths import AppPaths

        from backend.infrastructure.runtime.instance_lock import InstanceLock

        import tempfile

        from backend.infrastructure.db.sqlite_backup import SQLiteBackupService
        from backend.shared.ids import new_uuid

        paths = AppPaths.from_environment()
        lock = InstanceLock(paths.instance_lock_path)
        if not lock.acquire(timeout_seconds=30):
            report["packaging"].append("La base de datos está abierta por otra instancia.")
            raise RuntimeError("bootstrap")
        workdir = Path(tempfile.mkdtemp(prefix="spj-ui-self-test-"))
        copy = SQLiteBackupService().create(paths.database_path, workdir, label="ui-self-test",
                                            quiescent=False).path
        lock.release()
        lock = None
        report["database_copy"] = True
        set_db_path(str(copy))
        bootstrap = run_database_bootstrap_sequence(copy)
        if not bootstrap.success:
            failed = bootstrap.failed_step()
            report["packaging"].append(f"arranque de base: {failed.message if failed else '?'}")
            raise RuntimeError("bootstrap")
        connection = bootstrap.context.conn

        # ── login window ────────────────────────────────────────────────
        from frontend.desktop.app import _build_services
        from frontend.desktop.shell.desktop_shell_authentication_composition import (
            build_authentication_coordinator,
        )

        coordinator = build_authentication_coordinator(
            connection=connection, container=_build_services(),
            on_authenticated=lambda _context: None)
        login = coordinator._login_window_factory()
        login.show()
        _pump(app, 0.5)
        _grab(login, screenshots, "01_login", report)
        login.close()
        report["login_window"] = True

        # ── main window with every enabled route ────────────────────────
        from backend.application.software_updates.installation import enabled_capabilities_for
        from backend.bootstrap.application_context import (
            ApplicationContext,
            FeatureContext,
            default_workstation_id,
        )
        from backend.bootstrap.legacy_session_adapter import LegacySessionAdapter
        from frontend.desktop.shell.desktop_shell_window_composition import (
            build_application_window,
        )

        context = ApplicationContext(
            installation_id=new_uuid(), company_id=new_uuid(), branch_id=new_uuid(),
            branch_name="Autoprueba", workstation_id=default_workstation_id(),
            workstation_type="pos", user_id=new_uuid(), user_name="Autoprueba",
            roles=("admin",), permissions=frozenset({"*"}), feature_context=FeatureContext(),
            session_id=new_uuid(), capabilities=enabled_capabilities_for(paths))
        window = build_application_window(
            context=context, connection=connection,
            session_context=LegacySessionAdapter(context),
            health_report=bootstrap.health_report)
        if window.service_supervisor is not None:
            window.service_supervisor.stop_all()  # before ANY event is processed
        window.resize(1366, 768)
        window.show()
        _pump(app, 0.5)
        report["main_window"] = True
        routes = [item.route_id for item in window.sidebar._all_items] if window.sidebar else []
        from frontend.desktop.shell.loading.module_load_state import ModuleLoadState

        loader = window._module_loader
        for index, route_id in enumerate(routes, start=1):
            entry = {"route": route_id, "ok": False}
            try:
                route = window.router.route_registry.get(route_id)
                if loader is not None and route is not None:
                    load = loader.ensure_loaded(route.module_id)
                    if load.state is ModuleLoadState.FAILED:
                        raise load.error  # classified below like any other error
                result = window.navigate(route_id)
                if getattr(result, "load_failed", False):
                    raise RuntimeError(f"la ruta {route_id} mostró la vista de error del módulo")
                _pump(app, 0.3)
                entry["ok"] = True
                _grab(window, screenshots, f"{index + 1:02d}_{route_id.replace('.', '_')}", report)
            except _PACKAGING_ERRORS as exc:
                entry["error"] = f"{type(exc).__name__}: {exc}"
                report["packaging"].append(f"{route_id}: {entry['error']}")
            except Exception as exc:
                entry["error"] = f"{type(exc).__name__}: {exc}"
                report["route_warnings"].append(f"{route_id}: {entry['error']}")
            if slot_errors:
                entry.setdefault("slot_errors", []).extend(slot_errors)
                report["route_warnings"].extend(f"{route_id}: {e}" for e in slot_errors)
                slot_errors.clear()
            report["routes"].append(entry)
        window.close()

        _check_webengine(app, report)
        report["ui"] = True
        report["ok"] = not report["packaging"]
        report["detail"] = (f"{len(routes)} rutas, {sum(r['ok'] for r in report['routes'])} "
                            f"abiertas; WebEngine: {report['webengine']}")
    except Exception as exc:
        if str(exc) != "bootstrap":
            report["packaging"].append(f"{type(exc).__name__}: {exc}")
            report["traceback"] = traceback.format_exc()[-4000:]
    finally:
        sys.excepthook = previous_hook
        if connection is not None:
            try:
                connection.close()
            except Exception:
                pass
        if lock is not None:
            lock.release()
        if workdir is not None:
            import shutil

            from backend.infrastructure.db.connection import close_thread_connection

            close_thread_connection()
            shutil.rmtree(workdir, ignore_errors=True)
    _write(report, report_file)
    return 0 if report["ok"] else 1


#: Whole-run deadline. A stuck QtWebEngine render process once kept the
#: process alive ~44 minutes during Qt shutdown (2026-10-15, low-disk PC):
#: a self-test must END, with a verdict, in bounded time.
WATCHDOG_SECONDS = 15 * 60


def main(argv: list[str] | None = None) -> int:
    import threading

    argv = list(sys.argv if argv is None else argv)
    if sys.stderr is not None:
        logging.basicConfig(level=logging.WARNING, stream=sys.stderr)
    os.environ.setdefault("QT_ENABLE_HIGHDPI_SCALING", "1")
    report_file = _argument(argv, "--report")

    def _timeout() -> None:
        _write({"ok": False, "ui": False, "detail":
                f"La autoprueba de interfaz no terminó en {WATCHDOG_SECONDS} s.",
                "packaging": ["timeout"]}, report_file)
        os._exit(2)

    watchdog = threading.Timer(WATCHDOG_SECONDS, _timeout)
    watchdog.daemon = True
    watchdog.start()
    code = run_ui_self_test(argv)
    # The verdict is on disk: exit WITHOUT Qt/WebEngine teardown, which is
    # where a stuck render process can block for a long time.
    for stream in (sys.stdout, sys.stderr):
        if stream is not None:
            stream.flush()
    os._exit(code)
