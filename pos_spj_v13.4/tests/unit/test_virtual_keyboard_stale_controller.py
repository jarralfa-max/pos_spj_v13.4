"""Teclado virtual: un controlador ya destruido no tumba el diálogo (2026-09-19).

Qt reutiliza la dirección de un campo destruido y sip puede devolver el
envoltorio de Python VIEJO con su atributo `_keyboard_controller`, cuyo objeto
C++ ya no existe. `attach_virtual_keyboard_action` lo tocaba y reventaba con
"wrapped C/C++ object ... has been deleted" al construir cualquier diálogo con
campos de captura — intermitente en la suite (Delivery el 18, Descuento el 19).
"""
from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

QtWidgets = pytest.importorskip("PyQt5.QtWidgets", exc_type=ImportError)


@pytest.fixture(scope="module")
def app():
    return QtWidgets.QApplication.instance() or QtWidgets.QApplication([])


def test_un_controlador_destruido_se_reemplaza_sin_reventar(app):
    from PyQt5 import sip

    from frontend.desktop.components.virtual_keyboard import (
        KeyboardAwareInput,
        attach_virtual_keyboard_action,
    )

    campo = QtWidgets.QLineEdit()
    otro = QtWidgets.QLineEdit()
    muerto = KeyboardAwareInput(otro)
    sip.delete(muerto)          # su objeto C++ ya no existe; el envoltorio sí
    campo._keyboard_controller = muerto

    accion = attach_virtual_keyboard_action(campo)

    assert accion in campo.actions()
    assert not sip.isdeleted(campo._keyboard_controller)
