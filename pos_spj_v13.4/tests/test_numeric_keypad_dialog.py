# tests/test_numeric_keypad_dialog.py
"""Componente base NumericKeypadDialog (teclado numérico genérico).

Verifica la semántica de `permitir_cero` (montos que exigen > 0 vs capturas que
aceptan 0, p.ej. fondo de caja inicial) y la API get_value().
"""
import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PyQt5")

from PyQt5.QtWidgets import QApplication  # noqa: E402


@pytest.fixture(scope="module")
def _app():
    return QApplication.instance() or QApplication([])


def _dlg(**kw):
    from frontend.desktop.components.numeric_keypad_dialog import NumericKeypadDialog
    return NumericKeypadDialog(**kw)


def test_por_defecto_exige_mayor_que_cero(_app):
    dlg = _dlg(decimals=2, unidad="$")
    assert not dlg.btn_ok.isEnabled()      # vacío/0 no confirmable
    dlg._agregar_digito("5")
    assert dlg.btn_ok.isEnabled()


def test_permitir_cero_habilita_confirmar_cero(_app):
    # p.ej. fondo de caja inicial = 0
    dlg = _dlg(decimals=2, unidad="$", permitir_cero=True)
    assert dlg.valor() == 0.0
    assert dlg.btn_ok.isEnabled()          # 0 sí es confirmable


def test_porcentaje_respeta_maximo_100(_app):
    dlg = _dlg(decimals=1, maximo=100.0, unidad="%")
    for ch in "150":
        dlg._agregar_digito(ch)
    assert dlg.valor() <= 100.0


def test_valor_inicial_en_edicion(_app):
    dlg = _dlg(decimals=3, unidad="kg", inicial=2.5, permitir_cero=True)
    assert dlg.valor() == 2.5


def test_quantity_input_dialog_es_subclase(_app):
    from frontend.desktop.components.quantity_input_dialog import QuantityInputDialog
    from frontend.desktop.components.numeric_keypad_dialog import NumericKeypadDialog
    assert issubclass(QuantityInputDialog, NumericKeypadDialog)
    # get_quantity delega en get_value (nunca permite cero para cantidades)
    dlg = QuantityInputDialog(decimals=3)
    assert not dlg.btn_ok.isEnabled()
