"""Regresión — el login no debe cerrar la app en silencio.

Bug reportado: "si la contraseña o el usuario está incorrecto no muestra error,
solo se cierra la app".

Causa raíz confirmada:
  1. `mostrar_login()` oculta la ventana principal antes de abrir el diálogo.
     Si el diálogo se cierra sin autenticar (Escape/✕), la única ventana viva
     desaparece y `quitOnLastWindowClosed` mata la app ANTES de dar señal.
  2. Un fallo del audit trail dentro de `authenticate()` podía enmascarar el
     `PermissionError` de credenciales inválidas y escalar a excepción no
     controlada (que en PyQt aborta el proceso sin mostrar el mensaje).

Estos tests fijan ambos comportamientos.
"""
import os
import sqlite3

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


# ── Parte 1: authenticate() nunca deja que el audit enmascare el rechazo ──────

def _seeded_container(tmp_path):
    from migrations import engine
    db = str(tmp_path / "auth.db")
    conn = sqlite3.connect(db)
    engine.up(conn)
    conn.commit()
    conn.close()
    from core.app_container import AppContainer
    return AppContainer(db_path=db)


class _BoomAudit:
    """Sink de auditoría que siempre falla."""
    def log_change(self, **kwargs):
        raise RuntimeError("audit sink caído")


@pytest.mark.parametrize("usuario,password", [
    ("admin", "contraseña-incorrecta"),   # usuario existe, password mal
    ("no-existe", "lo-que-sea"),          # usuario inexistente
])
def test_credenciales_invalidas_lanzan_permission_error_aunque_audit_falle(
        tmp_path, usuario, password):
    container = _seeded_container(tmp_path)
    auth = container.auth_service
    auth.audit_service = _BoomAudit()   # el audit revienta en cada intento

    with pytest.raises(PermissionError) as exc:
        auth.authenticate(usuario, password)
    # Mensaje genérico y uniforme: no revela si falló el usuario o la contraseña.
    assert str(exc.value) == "Usuario o contraseña incorrectos."


def test_audit_safe_no_propaga(tmp_path):
    """El wrapper _audit_safe traga cualquier error del sink."""
    container = _seeded_container(tmp_path)
    auth = container.auth_service
    auth.audit_service = _BoomAudit()
    # No debe lanzar.
    auth._audit_safe(usuario="x", accion="LOGIN_FAILED", modulo="AUTH",
                     entidad="USUARIO", entidad_id="x", before_state={},
                     after_state={}, sucursal_id="", detalles="prueba")


# ── Parte 2: mostrar_login() no cierra la app en silencio ─────────────────────

@pytest.fixture(scope="module")
def qapp():
    PyQt5 = pytest.importorskip("PyQt5")
    from PyQt5.QtWidgets import QApplication
    return QApplication.instance() or QApplication([])


@pytest.fixture
def window(qapp, tmp_path):
    from migrations import engine
    db = str(tmp_path / "ui.db")
    conn = sqlite3.connect(db)
    engine.up(conn)
    conn.commit()
    conn.close()
    from core.app_container import AppContainer
    from interfaz.main_window import MainWindow
    return MainWindow(AppContainer(db_path=db))


def test_cancelar_login_cierra_limpio_sin_dialogo_extra(qapp, window, monkeypatch):
    """Cerrar el login sin autenticar (Escape/✕) cierra la app de forma limpia
    y explícita (app.quit), SIN un diálogo de confirmación adicional."""
    from PyQt5.QtWidgets import QDialog, QMessageBox
    from interfaz import main_window as mw

    monkeypatch.setattr(mw.DialogoLogin, "exec_", lambda self: QDialog.Rejected)

    # No debe aparecer ningún QMessageBox de confirmación.
    def _no_popup(*a, **k):
        pytest.fail("no debe mostrarse ningún diálogo extra al cancelar el login")
    monkeypatch.setattr(QMessageBox, "question", staticmethod(_no_popup))

    quits = {"n": 0}
    monkeypatch.setattr(qapp, "quit", lambda: quits.__setitem__("n", quits["n"] + 1))

    window.mostrar_login()

    assert quits["n"] == 1, "cancelar el login debe cerrar la app (app.quit)"
    assert window.usuario_actual is None


def test_login_correcto_muestra_ventana(qapp, window, monkeypatch):
    """Con credenciales válidas, el login procede y se muestra la ventana
    principal; la app nunca se cierra."""
    from PyQt5.QtWidgets import QDialog
    from interfaz import main_window as mw

    def fake_exec(self):
        self.usuario_autenticado = {"nombre": "Ana", "username": "ana", "rol": "admin"}
        return QDialog.Accepted
    monkeypatch.setattr(mw.DialogoLogin, "exec_", fake_exec)
    monkeypatch.setattr(qapp, "quit",
                        lambda: pytest.fail("un login correcto no debe cerrar la app"))

    window.mostrar_login()

    assert window.usuario_actual is not None
    assert window.usuario_actual.get("nombre") == "Ana"


# ── Parte 3: la tecla Enter valida el login, no cierra la app ─────────────────

@pytest.fixture
def login_dialog(qapp, tmp_path):
    from migrations import engine
    db = str(tmp_path / "login.db")
    conn = sqlite3.connect(db)
    engine.up(conn)
    conn.commit()
    conn.close()
    from core.app_container import AppContainer
    from interfaz.main_window import DialogoLogin
    return DialogoLogin(AppContainer(db_path=db).auth_service, None)


def test_boton_cerrar_no_es_default(login_dialog):
    """El ✕ no debe ser autoDefault/default; ENTRAR debe ser el default. Si el
    ✕ fuera el default, pulsar Enter cerraría la app en vez de validar."""
    from PyQt5.QtWidgets import QPushButton
    botones = {b.text(): b for b in login_dialog.findChildren(QPushButton)}
    assert botones["✕"].autoDefault() is False
    assert botones["✕"].isDefault() is False
    assert botones["ENTRAR AL SISTEMA"].isDefault() is True


def test_enter_con_password_vacia_muestra_error_y_no_cierra(login_dialog):
    """Escribir usuario, dejar la contraseña vacía y pulsar Enter debe mostrar
    el aviso inline y mantener el diálogo abierto (sin rechazarlo → sin cerrar
    la app)."""
    from PyQt5.QtCore import Qt
    from PyQt5.QtTest import QTest

    login_dialog.txt_usuario.setText("admin")
    login_dialog.txt_password.setText("")
    login_dialog.txt_usuario.setFocus()

    rechazos = {"n": 0}
    login_dialog.rejected.connect(lambda: rechazos.__setitem__("n", rechazos["n"] + 1))

    QTest.keyClick(login_dialog.txt_usuario, Qt.Key_Return)

    assert login_dialog.lbl_error.text().strip() != "", "debe mostrar un aviso"
    assert "usuario y contraseña" in login_dialog.lbl_error.text().lower()
    assert rechazos["n"] == 0, "Enter no debe cerrar/rechazar el diálogo"
