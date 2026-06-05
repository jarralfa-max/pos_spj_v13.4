import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


class _Flags:
    def __init__(self, enabled: bool) -> None:
        self.enabled = enabled

    def is_enabled(self, _key: str) -> bool:
        return self.enabled


def _button(menu, code: str):
    from PyQt5.QtWidgets import QPushButton

    for btn in menu.findChildren(QPushButton):
        if str(btn.property("modulo_codigo") or "") == code:
            return btn
    raise AssertionError(f"Missing menu button {code}")


def test_menu_lateral_respects_permissions_and_hidden_reasons() -> None:
    try:
        from PyQt5.QtWidgets import QApplication
    except ImportError as exc:
        pytest.skip(f"PyQt runtime unavailable: {exc}")

    from interfaz.menu_lateral import MenuLateral

    app = QApplication.instance() or QApplication([])
    menu = MenuLateral()
    pos = _button(menu, "POS")
    planning = _button(menu, "PLANEACION_COMPRAS")

    menu.set_permisos({"POS.ver"})
    assert pos.isVisible()

    menu.set_permisos(set())
    assert not pos.isVisible()
    assert menu.hidden_reason("POS") == "permission"

    menu.set_permisos({"*"})
    assert pos.isVisible()

    menu.set_permisos({"PLANEACION_COMPRAS.ver"})
    menu.set_module_config(_Flags(False))
    assert not planning.isVisible()
    assert menu.hidden_reason("PLANEACION_COMPRAS") == "feature_flag"

    menu.set_permisos(set())
    menu.set_module_config(_Flags(True))
    assert not planning.isVisible()
    assert menu.hidden_reason("PLANEACION_COMPRAS") == "permission"

    menu.deleteLater()
    app.processEvents()
