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

    with pytest.raises(PermissionError):
        auth.authenticate(usuario, password)


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


def test_reject_no_cierra_en_silencio_pide_confirmacion(qapp, window, monkeypatch):
    """Cerrar el login sin autenticar debe PREGUNTAR antes de salir, no
    desaparecer. Si el usuario confirma salir, se sale limpio (app.quit)."""
    from PyQt5.QtWidgets import QDialog, QMessageBox
    from interfaz import main_window as mw

    qapp.setQuitOnLastWindowClosed(True)
    monkeypatch.setattr(mw.DialogoLogin, "exec_", lambda self: QDialog.Rejected)

    pregunto = {"n": 0}
    def fake_question(*a, **k):
        pregunto["n"] += 1
        return QMessageBox.Yes   # el usuario decide salir
    monkeypatch.setattr(QMessageBox, "question", staticmethod(fake_question))

    quits = {"n": 0}
    monkeypatch.setattr(qapp, "quit", lambda: quits.__setitem__("n", quits["n"] + 1))

    window.mostrar_login()

    assert pregunto["n"] == 1, "debe confirmar la salida en vez de cerrarse solo"
    assert quits["n"] == 1, "al confirmar, la salida debe ser explícita (app.quit)"
    assert window.usuario_actual is None
    # El flag global debe quedar restaurado tras el login.
    assert qapp.quitOnLastWindowClosed() is True


def test_reject_y_reintento_permite_iniciar_sesion(qapp, window, monkeypatch):
    """Si el usuario cierra el diálogo pero decide quedarse (No), el login se
    vuelve a pedir y puede completarse; la app nunca se cierra."""
    from PyQt5.QtWidgets import QDialog, QMessageBox
    from interfaz import main_window as mw

    resultados = [QDialog.Rejected, QDialog.Accepted]
    def fake_exec(self):
        r = resultados.pop(0)
        if r == QDialog.Accepted:
            self.usuario_autenticado = {
                "nombre": "Ana", "username": "ana", "rol": "admin",
            }
        return r
    monkeypatch.setattr(mw.DialogoLogin, "exec_", fake_exec)
    monkeypatch.setattr(QMessageBox, "question",
                        staticmethod(lambda *a, **k: QMessageBox.No))  # quedarse
    monkeypatch.setattr(qapp, "quit",
                        lambda: pytest.fail("no debe salir si el usuario reintenta"))

    window.mostrar_login()

    assert window.usuario_actual is not None
    assert window.usuario_actual.get("nombre") == "Ana"
