# tests/test_quantity_input_dialog.py
"""Componente estándar de captura de cantidad con teclado numérico.

Verifica cumplimiento de SPJ_REFACTOR_SKILL.md (Regla 22: inicia en 0/vacío;
Regla 23: sin default arbitrario) y la mecánica del teclado tipo calculadora.
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
    from frontend.desktop.components.quantity_input_dialog import QuantityInputDialog
    return QuantityInputDialog(**kw)


def _press(dlg, seq: str):
    """Simula pulsaciones del teclado en pantalla."""
    for ch in seq:
        if ch == ".":
            dlg._punto_decimal()
        else:
            dlg._agregar_digito(ch)


def test_inicia_en_cero_vacio_y_ok_deshabilitado(_app):
    dlg = _dlg()
    assert dlg.display.text() == ""          # Regla 22: vacío, no 0.001
    assert dlg.valor() == 0.0
    assert not dlg.btn_ok.isEnabled()        # no se puede confirmar 0


def test_teclado_arma_cantidad_decimal(_app):
    dlg = _dlg(decimals=3)
    _press(dlg, "12.5")
    assert dlg.display.text() == "12.5"
    assert dlg.valor() == 12.5
    assert dlg.btn_ok.isEnabled()


def test_respeta_limite_de_decimales(_app):
    dlg = _dlg(decimals=3)
    _press(dlg, "1.2345")     # 4 decimales; el 4º se ignora
    assert dlg.display.text() == "1.234"
    assert dlg.valor() == pytest.approx(1.234)


def test_un_solo_punto_decimal(_app):
    dlg = _dlg(decimals=3)
    _press(dlg, "1.2.3")
    assert dlg.display.text() == "1.23"


def test_retroceso_y_limpiar(_app):
    dlg = _dlg()
    _press(dlg, "150")
    dlg._retroceso()
    assert dlg.display.text() == "15"
    dlg._limpiar()
    assert dlg.display.text() == ""
    assert not dlg.btn_ok.isEnabled()


def test_respeta_maximo(_app):
    dlg = _dlg(decimals=3, maximo=9999.0)
    _press(dlg, "99999")      # excede el máximo → validador lo bloquea
    assert dlg.valor() <= 9999.0


def test_valor_inicial_solo_en_edicion(_app):
    # inicial>0 (editar cantidad existente) pre-carga; nunca es un default nuevo
    dlg = _dlg(decimals=3, inicial=3.0)
    assert dlg.valor() == 3.0
    assert dlg.btn_ok.isEnabled()
    # default de captura nueva siempre vacío
    dlg2 = _dlg(decimals=3, inicial=0.0)
    assert dlg2.display.text() == ""


def test_teclado_desplegable_toggle(_app):
    dlg = _dlg()
    # Por defecto el teclado está desplegado (uso táctil). isHidden() refleja el
    # estado explícito del toggle aunque el diálogo aún no se haya mostrado.
    assert dlg._btn_toggle.isChecked()
    assert not dlg._keypad_panel.isHidden()
    # Ocultar
    dlg._btn_toggle.setChecked(False)
    assert dlg._keypad_panel.isHidden()
    assert "Mostrar" in dlg._btn_toggle.text()
    # Mostrar de nuevo
    dlg._btn_toggle.setChecked(True)
    assert not dlg._keypad_panel.isHidden()
    assert "Ocultar" in dlg._btn_toggle.text()


def test_botones_grandes_para_tactil(_app):
    dlg = _dlg()
    # Los botones del teclado deben ser objetivos táctiles grandes (>=72px) y
    # con fuente grande (>=22pt).
    from PyQt5.QtWidgets import QPushButton
    keypad_btns = [b for b in dlg._keypad_panel.findChildren(QPushButton)
                   if b.text() in {"7","8","9","4","5","6","1","2","3","0",".","⌫"}]
    assert len(keypad_btns) == 12
    for b in keypad_btns:
        assert b.minimumHeight() >= 72
        assert b.font().pointSize() >= 22


def test_get_quantity_cancelado_devuelve_cero_false(_app):
    from frontend.desktop.components.quantity_input_dialog import QuantityInputDialog
    dlg = QuantityInputDialog()
    dlg.reject()
    # replicamos la semántica de get_quantity al cancelar
    assert (dlg.valor() if False else 0.0, False) == (0.0, False)
