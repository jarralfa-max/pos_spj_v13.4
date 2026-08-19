"""Smoke del host enterprise: ModuloProductosEnterprise arma el shell con SideNav."""

import os
import sqlite3

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt5.QtWidgets import QApplication  # noqa: E402

from backend.infrastructure.db.schema.products_schema import create_products_schema  # noqa: E402


class _Container:
    def __init__(self, conn):
        self.db = conn
        self.usuario = "u1"
        self.sucursal_id = "1"
        self.session = None  # sin sesión viva → política permisiva (arranque)


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


def test_host_builds_sidebar_shell(app):
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    create_products_schema(conn)
    conn.commit()
    from modulos.productos_enterprise import ModuloProductosEnterprise

    host = ModuloProductosEnterprise(_Container(conn))
    # El shell expone la navegación lateral con las 7 secciones y la primera activa
    # (P0-B slice 7 añadió "Sucursales y canales").
    assert host._view.nav.count() == 7
    assert host._view.stack.currentIndex() == 0
    labels = [host._view.nav.item(i).text() for i in range(host._view.nav.count())]
    assert labels == ["Resumen", "Catálogo", "Categorías", "Marcas", "Atributos",
                      "Sucursales y canales", "Importar"]
    conn.close()


class _BareContainer:
    """Sin usuario ni sucursal ni sesión (arranque sin login)."""

    def __init__(self, conn):
        self.db = conn


def test_no_invented_identity_when_no_session(app):
    # §21.2 fail-closed: sin sesión NO se fabrica identidad ("desktop"/"1").
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    create_products_schema(conn)
    conn.commit()
    from modulos.productos_enterprise import ModuloProductosEnterprise

    host = ModuloProductosEnterprise(_BareContainer(conn))
    # el shell se construye (lectura), pero la identidad queda vacía, no inventada
    assert host._session.user_id is None
    assert host._session.branch_id is None
    conn.close()


class _FakeLiveSession:
    """Doble mínimo de SessionContext: sólo expone `user_id` (§21.2)."""
    def __init__(self, user_id):
        self.user_id = user_id

    def tiene_permiso(self, _code):
        return True


class _ContainerWithRealSession:
    """Contenedor con sesión viva autenticada (caso real de producción)."""

    def __init__(self, conn, user_id):
        self.db = conn
        self.sucursal_id = "b1"
        self.session = _FakeLiveSession(user_id)
        # `usuario`/`usuario_actual` NUNCA existen en AppContainer real — no se
        # definen aquí a propósito, para probar que ya no se leen.


def test_identity_comes_from_live_session_user_id(app):
    """Regresión: la identidad para ciclo de vida debe venir de
    `container.session.user_id` (SessionContext real), no de los atributos
    inexistentes `container.usuario`/`usuario_actual` (bug real reportado en
    producción: activar un producto fallaba con "Operación sin usuario
    autenticado" pese a haber una sesión autenticada)."""
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    create_products_schema(conn)
    conn.commit()
    from modulos.productos_enterprise import ModuloProductosEnterprise

    host = ModuloProductosEnterprise(_ContainerWithRealSession(conn, "user-abc-123"))
    assert host._session.user_id == "user-abc-123"
    assert host._session.branch_id == "b1"
    conn.close()


def test_identity_resolves_live_not_at_construction_time(app):
    """Regresión del bug real: `MainWindow._construir_todas_las_pantallas()`
    construye este módulo dentro de `__init__`, ANTES del login (el login se
    dispara después vía `QTimer.singleShot(0, self.mostrar_login)`). Una
    identidad tomada como foto fija en el constructor queda vacía para
    siempre. Prueba exactamente ese orden: construir el módulo SIN sesión
    autenticada (login aún no ha corrido), luego mutar el MISMO objeto de
    sesión (como hace `iniciar_sesion`/`set_permisos` en producción) y
    verificar que la identidad expuesta por el módulo cambia — no se congeló
    en el constructor."""
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    create_products_schema(conn)
    conn.commit()
    from modulos.productos_enterprise import ModuloProductosEnterprise

    live_session = _FakeLiveSession(user_id=None)  # aún sin login, como al arranque
    container = _ContainerWithRealSession(conn, user_id=None)
    container.session = live_session

    host = ModuloProductosEnterprise(container)
    assert host._session.user_id is None  # antes del login: sin identidad

    live_session.user_id = "user-post-login"  # el login muta la MISMA sesión
    assert host._session.user_id == "user-post-login"  # ya no está congelada
    conn.close()
