"""Exercise the real entry point with modal dialogs replaced by deterministic answers."""
import importlib.util
from pathlib import Path
from unittest.mock import Mock

import pytest
from PyQt5.QtWidgets import QDialog


@pytest.fixture
def entrypoint(monkeypatch, tmp_path):
    import core.logging_setup
    import backend.infrastructure.db.connection

    monkeypatch.setattr(core.logging_setup, "setup_logging", lambda: None)
    monkeypatch.setattr(backend.infrastructure.db.connection, "set_db_path", lambda path: None)
    path = Path(__file__).resolve().parents[3] / "main.py"
    spec = importlib.util.spec_from_file_location("remediation_entrypoint", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    import ui.themes.theme_engine
    import modulos.ui_components

    monkeypatch.setattr(ui.themes.theme_engine, "load_saved_theme", lambda connection: None)
    monkeypatch.setattr(modulos.ui_components, "install_dialog_button_normalizer", lambda app: None)
    monkeypatch.setattr(module, "DB_PATH", str(tmp_path / "startup.db"))
    monkeypatch.setattr(module, "_instancia_unica", lambda app: True)
    monkeypatch.setattr(module, "QApplication", Mock(return_value=Mock()))
    monkeypatch.setattr(module, "QMessageBox", Mock())
    monkeypatch.setattr(module, "AppContainer", Mock(side_effect=AssertionError("operational services started")))
    monkeypatch.setattr(module, "MainWindow", Mock(side_effect=AssertionError("operational UI started")))
    return module


def test_main_exits_before_operational_services_when_setup_is_cancelled(entrypoint, monkeypatch):
    from frontend.desktop.shell import desktop_shell_authentication_composition as composition

    wizard = Mock()
    wizard.exec_.return_value = QDialog.Rejected
    factory = Mock(return_value=wizard)
    monkeypatch.setattr(composition, "InitialSetupWizard", factory)

    with pytest.raises(SystemExit) as exit_result:
        entrypoint.inicializar_sistema()

    assert exit_result.value.code == 0
    factory.assert_called_once()
    wizard.exec_.assert_called_once()
    entrypoint.AppContainer.assert_not_called()
    entrypoint.MainWindow.assert_not_called()


def test_main_does_not_open_setup_or_ui_after_migration_failure(entrypoint, monkeypatch):
    from migrations import engine
    from backend.bootstrap import installation_setup

    monkeypatch.setattr(engine, "MIGRATIONS", [engine._Migration("missing", "missing_required_spj_migration")])
    setup = Mock(side_effect=AssertionError("setup opened after schema failure"))
    monkeypatch.setattr(installation_setup, "ensure_installation_provisioned", setup)

    with pytest.raises(SystemExit) as exit_result:
        entrypoint.inicializar_sistema()

    assert exit_result.value.code == 1
    setup.assert_not_called()
    entrypoint.AppContainer.assert_not_called()
    entrypoint.MainWindow.assert_not_called()
