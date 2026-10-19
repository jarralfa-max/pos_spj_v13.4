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
    app_module.QMessageBox.critical.assert_called_once()
