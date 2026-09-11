"""El arranque de escritorio llega hasta el login (§62, meta del PASS 2).

Recorre la MISMA secuencia que `frontend.desktop.app.main()` — base de datos,
grafo de dependencias, coordinador de autenticación, ventana de login — sobre
una base temporal. No se muestra ninguna ventana: se construyen, que es donde
aparecen los `ModuleNotFoundError` y los fallos de composición.

Vale la pena tenerlo aunque parezca trivial: durante toda la reconstrucción, lo
que rompía el arranque no era la lógica sino un import a una carpeta borrada,
tres niveles por debajo de donde se estaba mirando.
"""
from __future__ import annotations

import pytest

pytest.importorskip("PyQt5")


@pytest.fixture(scope="module")
def qapp():
    from PyQt5.QtCore import Qt
    from PyQt5.QtWidgets import QApplication

    QApplication.setAttribute(Qt.AA_ShareOpenGLContexts)
    app = QApplication.instance() or QApplication([])
    yield app


@pytest.fixture(scope="module")
def arranque(tmp_path_factory, qapp, monkeypatch_module):
    """Ejecuta la preparación de base de datos sobre una copia temporal.

    Se reapunta `DB_PATH`/`DATA_DIR` del módulo: `_prepare_database()` los lee
    como constantes, y ejecutar esto contra la base real migraría la base real.
    """
    import frontend.desktop.app as app

    destino = tmp_path_factory.mktemp("arranque")
    monkeypatch_module.setattr(app, "DATA_DIR", str(destino / "data"))
    monkeypatch_module.setattr(app, "DB_PATH", str(destino / "data" / "spj_pos_database.db"))
    monkeypatch_module.setattr(app, "LOGS_DIR", str(destino / "logs"))
    return app._prepare_database()


@pytest.fixture(scope="module")
def monkeypatch_module():
    from _pytest.monkeypatch import MonkeyPatch

    patcher = MonkeyPatch()
    yield patcher
    patcher.undo()


def test_database_bootstrap_succeeds(arranque):
    from backend.bootstrap.bootstrap_state import BootstrapState

    assert arranque.success is True
    assert arranque.final_state is BootstrapState.RUNNING
    assert arranque.context.conn is not None


def test_bootstrap_produces_a_real_health_report(arranque):
    """El menú lateral lee `report.checks`; un `None` reventaría tras el login."""
    assert arranque.health_report is not None
    assert arranque.health_report.checks


def test_dependency_graph_builds_and_resolves_security_policies(arranque):
    """`CompositionRoot` valida el grafo entero al construirlo."""
    import frontend.desktop.app as app
    from backend.security.credentials.password_policy import PasswordPolicy
    from backend.security.sessions.account_lockout_policy import AccountLockoutPolicy

    services = app._build_services()
    assert services.resolve(PasswordPolicy) is not None
    assert services.resolve(AccountLockoutPolicy) is not None


def test_authentication_coordinator_and_login_window_build(arranque):
    """El punto exacto que fija el PASS 2: se llega a construir el login."""
    import frontend.desktop.app as app
    from frontend.desktop.auth.login_window import LoginWindow
    from frontend.desktop.shell.desktop_shell_authentication_composition import (
        build_authentication_coordinator,
    )

    coordinator = build_authentication_coordinator(
        connection=arranque.context.conn,
        container=app._build_services(),
        on_authenticated=lambda _context: None,
    )
    assert coordinator._installation_status_query.current_status() is not None
    assert isinstance(coordinator._login_window_factory(), LoginWindow)


def test_app_root_points_at_the_project_root_not_a_level_above_or_below():
    """El error silencioso: contar mal los niveles desde `frontend/desktop/`.

    No lanza ninguna excepción — simplemente crea la base de datos en otra
    carpeta y la aplicación arranca vacía, como si fuera una instalación nueva,
    con los datos reales intactos pero invisibles. Por eso se comprueba contra
    un ancla que sólo existe en la raíz de verdad.
    """
    import os

    import frontend.desktop.app as app

    # Sólo se mira `APP_ROOT`: `DB_PATH` lo reapunta la fixture `arranque` para
    # no migrar la base real, así que leerlo aquí mediría el parche y no el
    # código. `APP_ROOT` nunca se parchea, y es de donde `DB_PATH` se deriva.
    assert os.path.isfile(os.path.join(app.APP_ROOT, "main.py"))
    assert os.path.isdir(os.path.join(app.APP_ROOT, "backend"))
    assert os.path.isdir(os.path.join(app.APP_ROOT, "frontend"))


def test_main_module_is_only_a_launcher():
    """§0: `main.py` no compone nada; sólo llama a `frontend.desktop.app.main`."""
    import ast
    from pathlib import Path

    fuente = (Path(__file__).resolve().parents[3] / "main.py").read_text(encoding="utf-8")
    arbol = ast.parse(fuente)

    modulos = {
        node.module for node in ast.walk(arbol)
        if isinstance(node, ast.ImportFrom) and node.module and not node.level
    } | {
        alias.name for node in ast.walk(arbol)
        if isinstance(node, ast.Import) for alias in node.names
    }
    assert modulos == {"os", "sys", "frontend.desktop.app"}, modulos
