"""P0-A fix — Inventario's PyQt shell uses the live session directly.

``ModuloInventarioEnterprise`` used to freeze a private ``_Session`` copy of
user_id/branch_id at construction time (before login could complete) and
fabricated ``warehouse_id = branch_id`` — both forbidden by §5.4 (no fabricated
identity/scope, no warehouse_id = branch_id). It now passes ``container.session``
straight through: the same live object the rest of the system observes, so a
login/branch switch that happens after construction is reflected without
rebuilding the widget, and an unset warehouse stays empty instead of silently
becoming the branch.
"""

from __future__ import annotations

import sqlite3

import pytest

from backend.infrastructure.db.schema.inventory_schema import create_inventory_schema
from core.session_context import SessionContext


class _Container:
    pass


@pytest.fixture
def conn():
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    create_inventory_schema(c)
    c.commit()
    return c


def test_module_uses_the_live_session_instance_not_a_frozen_copy(conn):
    pytest.importorskip("PyQt5")
    from PyQt5.QtWidgets import QApplication
    from modulos.inventario_enterprise import ModuloInventarioEnterprise

    app = QApplication.instance() or QApplication([])
    container = _Container()
    container.db = conn
    container.session = SessionContext()
    container.session.set_user({
        "id": "u1", "username": "ana", "nombre": "Ana",
        "rol": "gerente", "sucursal_id": "b1",
    })

    widget = ModuloInventarioEnterprise(container)
    assert widget._session is container.session

    presenter = widget._presenter
    assert presenter.default_branch() == "b1"
    # El almacén nunca se fijó en la sesión — debe quedar vacío, jamás caer en
    # la sucursal (§5.4: prohibido warehouse_id = branch_id).
    assert presenter.default_warehouse() == ""

    # Un cambio de sucursal posterior a la construcción (login que completa
    # después, o cambio de sucursal del usuario) se observa en vivo — no hace
    # falta reconstruir el widget.
    container.session.set_sucursal("b2", nombre="Sucursal 2")
    assert presenter.default_branch() == "b2"

    container.session.set_warehouse("w1", name="Almacén 1")
    assert presenter.default_warehouse() == "w1"

    del widget
    del app


def test_module_degrades_to_empty_scope_without_a_session(conn):
    """Sin container.session (arnés de prueba mínimo) no se fabrica identidad."""
    pytest.importorskip("PyQt5")
    from PyQt5.QtWidgets import QApplication
    from modulos.inventario_enterprise import ModuloInventarioEnterprise

    app = QApplication.instance() or QApplication([])
    container = _Container()
    container.db = conn

    widget = ModuloInventarioEnterprise(container)
    assert widget._session is None

    presenter = widget._presenter
    assert presenter.default_branch() == ""
    assert presenter.default_warehouse() == ""

    del widget
    del app
