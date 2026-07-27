import os
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

MENU = Path("pos_spj_v13.4/interfaz/menu_lateral.py")


def _button(menu, code: str):
    from PyQt5.QtWidgets import QPushButton

    for btn in menu.findChildren(QPushButton):
        if str(btn.property("modulo_codigo") or "") == code:
            return btn
    raise AssertionError(f"Missing menu button {code}")


def test_menu_source_has_no_role_visibility_matrix() -> None:
    content = MENU.read_text(encoding="utf-8")
    assert "SOLO_ADMIN_GERENTE" not in content
    assert "SOLO_ADMIN" not in content
    assert "GERENTE_O_SUPERIOR" not in content
    assert 'f"{codigo}.ver"' in content
    assert 'f"{codigo}.acceder"' in content


def test_menu_visibility_uses_permissions() -> None:
    try:
        from PyQt5.QtWidgets import QApplication
    except ImportError as exc:
        pytest.skip(f"PyQt runtime unavailable: {exc}")

    from interfaz.menu_lateral import MenuLateral

    app = QApplication.instance() or QApplication([])
    menu = MenuLateral()
    pos = _button(menu, "POS")
    caja = _button(menu, "CAJA")
    logout = _button(menu, "LOGOUT")

    menu.set_permisos({"POS.ver"}, rol="admin")
    assert pos.isVisible()
    assert not caja.isVisible()
    assert logout.isVisible()

    menu.set_permisos({"POS.acceder"}, rol="cajero")
    assert pos.isVisible()

    menu.set_permisos(set(), rol="admin")
    assert not pos.isVisible()
    assert logout.isVisible()

    menu.set_permisos({"*"}, rol="cajero")
    assert pos.isVisible()
    assert caja.isVisible()
    menu.deleteLater()
    app.processEvents()
