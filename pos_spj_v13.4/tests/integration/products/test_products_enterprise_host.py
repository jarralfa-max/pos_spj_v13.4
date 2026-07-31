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
