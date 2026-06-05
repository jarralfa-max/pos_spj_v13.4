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


def test_feature_flags_only_hide_and_never_grant_access() -> None:
    try:
        from PyQt5.QtWidgets import QApplication
    except ImportError as exc:
        pytest.skip(f"PyQt runtime unavailable: {exc}")

    from interfaz.menu_lateral import MenuLateral

    app = QApplication.instance() or QApplication([])
    menu = MenuLateral()
    planning = _button(menu, "PLANEACION_COMPRAS")

    menu.set_permisos(set())
    menu.set_module_config(_Flags(True))
    assert not planning.isVisible()

    menu.set_permisos({"PLANEACION_COMPRAS.ver"})
    menu.set_module_config(_Flags(False))
    assert not planning.isVisible()

    menu.set_permisos({"PLANEACION_COMPRAS.ver"})
    menu.set_module_config(_Flags(True))
    assert planning.isVisible()
    menu.deleteLater()
    app.processEvents()
