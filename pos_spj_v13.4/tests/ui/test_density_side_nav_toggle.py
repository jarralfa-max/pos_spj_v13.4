"""The manually positioned module toggle follows density without covering rows."""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PyQt5 import sip
from PyQt5.QtCore import QSize, Qt
from PyQt5.QtTest import QSignalSpy, QTest

from frontend.desktop.components.icons import Icons
from frontend.desktop.components.side_nav import SideNav
from frontend.desktop.themes.theme_manager import ThemeManager
from frontend.desktop.themes.tokens import density_metrics


@pytest.mark.parametrize("theme", ["light", "dark"])
@pytest.mark.parametrize("collapsed", [False, True])
def test_toggle_shrinks_after_touch_and_keeps_rows_reachable(
    qt_font_resources, monkeypatch, theme, collapsed,
):
    app = qt_font_resources
    manager = ThemeManager()
    monkeypatch.setattr(ThemeManager, "_instance", manager)
    manager.apply(app, theme, density="comfortable")
    nav = SideNav()
    nav.add_section("Productos", Icons.PRODUCTS)
    nav.add_section("Inventario", Icons.INVENTORY)
    nav.select(1)
    nav.set_collapsed(collapsed)
    nav.resize(64 if collapsed else 220, 400)
    nav.show()
    nav.setFocus(Qt.OtherFocusReason)
    navigation = QSignalSpy(nav.navigated)
    try:
        for density in ("comfortable", "touch", "compact", "comfortable"):
            manager.set_density(density, app=app)
            for height in (400, 220):
                nav.resize(nav.width(), height)
                for _ in range(4):
                    app.processEvents()
                size = density_metrics(density).icon_button_size
                assert nav._toggle.size() == QSize(size, size)
                assert nav.rect().contains(nav._toggle.geometry())
                assert not nav._toggle.geometry().intersects(nav.viewport().geometry())
                assert nav.currentRow() == 1
                assert nav.collapsed is collapsed
                assert not nav.item(0).icon().isNull()
                assert not nav.item(1).icon().isNull()
        assert len(navigation) == 0
        QTest.mouseClick(
            nav.viewport(), Qt.LeftButton,
            pos=nav.visualItemRect(nav.item(0)).center(),
        )
        assert nav.currentRow() == 0
        assert list(navigation) == [[0]]
        assert nav.collapsed is collapsed
    finally:
        nav.close()
        sip.delete(nav)
        manager.apply(app, "light", density="comfortable")
