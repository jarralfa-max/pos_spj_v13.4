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
    # El shell expone la navegación lateral con las 6 secciones y la primera activa.
    assert host._view.nav.count() == 6
    assert host._view.stack.currentIndex() == 0
    labels = [host._view.nav.item(i).text() for i in range(host._view.nav.count())]
    assert labels == ["Resumen", "Catálogo", "Categorías", "Marcas", "Atributos",
                      "Importar"]
    conn.close()
