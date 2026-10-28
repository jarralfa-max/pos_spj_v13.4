"""Compuertas del arranque real (`frontend/desktop/app.main`).

Reescrita el 2026-10-16: la versión anterior ejercitaba el `main.py` legacy
(`inicializar_sistema`, `AppContainer`, `MainWindow`, `core.logging_setup`),
borrado con la carpeta `core/`; desde entonces fallaba al importar y no probaba
nada. Las dos reglas que protegía siguen siendo del arranque actual:

1. si el arranque se cancela antes del login (asistente de primer arranque
   cancelado, instalación bloqueada), se sale con 0 SIN construir la ventana ni
   entrar al ciclo de eventos;
2. si la base no se pudo preparar (migración fallida), se sale con 1 SIN abrir
   el asistente ni el login.
"""

from __future__ import annotations

import sqlite3
from types import SimpleNamespace
from unittest.mock import Mock

import pytest


@pytest.fixture
def app_module(monkeypatch):
    from frontend.desktop import app

    monkeypatch.setattr(app, "QApplication", Mock(return_value=Mock()))
    monkeypatch.setattr(app, "QMessageBox", Mock())
    from frontend.desktop.components import dialogs
    monkeypatch.setattr(dialogs, "MessageDialog", Mock())
    monkeypatch.setattr(app, "_install_crash_handler", lambda: None)
    monkeypatch.setattr(app, "_update_gate_allows_start", lambda: True)
    monkeypatch.setattr(app, "_acquire_instance_lock", lambda: True)
    monkeypatch.setattr(app, "_relocate_legacy_database", lambda: True)
    monkeypatch.setattr(app, "_record_station_start", lambda connection: None)
    monkeypatch.setattr(app, "_build_services", lambda: Mock())
    monkeypatch.setattr(app, "_PATHS_ERROR", None)
    import frontend.desktop.logging_setup as logging_setup
    monkeypatch.setattr(logging_setup, "configure_logging", lambda *a, **k: None)
    from frontend.desktop.components import branding
    monkeypatch.setattr(branding.BrandAssetProvider, "apply_to_application",
                        staticmethod(lambda application: None))
    from backend.bootstrap.wiring import event_wiring
    monkeypatch.setattr(event_wiring, "wire_cross_context_events", lambda connection: {})
    return app


def test_cancelled_setup_exits_without_window_or_event_loop(app_module, monkeypatch):
    connection = sqlite3.connect(":memory:")
    monkeypatch.setattr(app_module, "_prepare_database", lambda: SimpleNamespace(
        context=SimpleNamespace(conn=connection), health_report=None))
    coordinator = Mock()
    coordinator.run.return_value = False            # asistente cancelado / instalación bloqueada
    from frontend.desktop.shell import desktop_shell_authentication_composition as auth
    monkeypatch.setattr(auth, "build_authentication_coordinator",
                        lambda **kwargs: coordinator)
    from frontend.desktop.shell import desktop_shell_window_composition as window
    build_window = Mock(side_effect=AssertionError("se construyó la ventana"))
    monkeypatch.setattr(window, "build_application_window", build_window)

    assert app_module.main() == 0

    coordinator.run.assert_called_once()
    build_window.assert_not_called()
    app_module.QApplication.return_value.exec_.assert_not_called()


def test_failed_migration_exits_before_setup_or_login(app_module, monkeypatch):
    from backend.bootstrap import run_database_bootstrap

    failed_step = SimpleNamespace(step_name="migrations", message="migración 999 falló")
    monkeypatch.setattr(run_database_bootstrap, "run_database_bootstrap_sequence",
                        lambda path: SimpleNamespace(
                            success=False, failed_step=lambda: failed_step,
                            context=SimpleNamespace(conn=None), warnings=()))
    import backend.infrastructure.db.connection as db_connection
    monkeypatch.setattr(db_connection, "set_db_path", lambda path: None)
    from frontend.desktop.shell import desktop_shell_authentication_composition as auth
    coordinator = Mock(side_effect=AssertionError("se abrió el asistente o el login"))
    monkeypatch.setattr(auth, "build_authentication_coordinator", coordinator)

    with pytest.raises(SystemExit) as exit_result:
        app_module.main()

    assert exit_result.value.code == 1
    coordinator.assert_not_called()
    from frontend.desktop.components.dialogs import MessageDialog
    MessageDialog.critical.assert_called_once()
    app_module.QMessageBox.critical.assert_not_called()


@pytest.mark.parametrize("outcome", ["cancel", "normal", "event_error", "services_error"])
def test_every_exit_closes_connections_before_releasing_instance(app_module, monkeypatch, outcome):
    connection = sqlite3.connect(":memory:")
    events = []
    monkeypatch.setattr(app_module, "_prepare_database", lambda: SimpleNamespace(
        context=SimpleNamespace(conn=connection), health_report=None))
    import backend.infrastructure.db.connection as db_connection
    monkeypatch.setattr(db_connection, "close_thread_connection", lambda: events.append("pool_closed"))

    def release():
        with pytest.raises(sqlite3.ProgrammingError, match="closed"):
            connection.execute("SELECT 1")
        events.append("lock_released")

    monkeypatch.setattr(app_module, "_release_instance_lock", release)
    from frontend.desktop.shell import desktop_shell_authentication_composition as auth
    coordinator = Mock()
    coordinator.run.return_value = outcome != "cancel"
    monkeypatch.setattr(auth, "build_authentication_coordinator", lambda **kwargs: coordinator)
    app_module.QApplication.return_value.exec_.return_value = 0
    if outcome == "event_error":
        app_module.QApplication.return_value.exec_.side_effect = RuntimeError("event loop failed")
    if outcome == "services_error":
        monkeypatch.setattr(app_module, "_build_services", Mock(side_effect=RuntimeError("services failed")))
    try:
        if outcome.endswith("error"):
            with pytest.raises(RuntimeError):
                app_module.main()
        else:
            assert app_module.main() == 0
        assert events == ["pool_closed", "lock_released"]
    finally:
        connection.close()


def test_database_failure_still_releases_instance_lock(app_module, monkeypatch):
    monkeypatch.setattr(app_module, "_prepare_database", Mock(side_effect=SystemExit(1)))
    release = Mock()
    monkeypatch.setattr(app_module, "_release_instance_lock", release)
    with pytest.raises(SystemExit):
        app_module.main()
    release.assert_called_once()


def test_worker_stop_failure_does_not_skip_database_cleanup(app_module, monkeypatch):
    connection = sqlite3.connect(":memory:")
    window = Mock()
    window.service_supervisor.stop_all.side_effect = RuntimeError("worker failed")
    import backend.infrastructure.db.connection as db_connection
    pool_close = Mock()
    monkeypatch.setattr(db_connection, "close_thread_connection", pool_close)
    app_module._shutdown_desktop_resources({"window": window, "connection": connection})
    pool_close.assert_called_once()
    with pytest.raises(sqlite3.ProgrammingError, match="closed"):
        connection.execute("SELECT 1")


@pytest.mark.parametrize("launch_fails", [False, True])
def test_update_handoff_keeps_resources_until_exit_and_recovers_if_launch_fails(app_module, monkeypatch, launch_fails):
    from backend.application.software_updates.installation import SoftwareInstallation
    from backend.infrastructure.updater import update_launcher
    from backend.infrastructure.db import sqlite_backup

    monkeypatch.setattr(SoftwareInstallation, "describe", lambda paths: Mock())
    launcher = Mock()
    if launch_fails:
        launcher.launch.side_effect = RuntimeError("launch failed")
    monkeypatch.setattr(update_launcher, "ExternalUpdaterLauncher", lambda installation: launcher)
    monkeypatch.setattr(sqlite_backup, "checkpoint_wal", lambda connection: True)
    release = Mock()
    monkeypatch.setattr(app_module, "_release_instance_lock", release)
    app, window, connection = Mock(), Mock(), Mock()
    request = SimpleNamespace(job_path="pending-update.json", job=SimpleNamespace(to_version="test"))
    handoff = app_module._make_update_handoff(app, connection, {"window": window})

    assert handoff(request) is (not launch_fails)
    window.service_supervisor.stop_all.assert_called_once()
    launcher.launch.assert_called_once()
    connection.close.assert_not_called()
    release.assert_not_called()
    if launch_fails:
        app.quit.assert_not_called()
        window.service_supervisor.start_all.assert_called_once()
    else:
        app.quit.assert_called_once()
        window.service_supervisor.start_all.assert_not_called()
