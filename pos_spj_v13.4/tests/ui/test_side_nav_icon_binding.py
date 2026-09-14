"""Open flyouts must keep semantic icons and stable permitted destinations."""
from PyQt5.QtCore import QEvent, QPoint, Qt
from PyQt5.QtGui import QIcon

from frontend.desktop.components.icons import IconProvider, Icons
from frontend.desktop.components.side_nav import SideNav
from frontend.desktop.themes.theme_manager import ThemeManager


def test_open_flyout_refreshes_icons_and_preserves_destinations(qt_font_resources, monkeypatch):
    app = qt_font_resources
    manager = ThemeManager()
    monkeypatch.setattr(ThemeManager, "_instance", manager)
    manager.apply(app, "light")
    nav = SideNav()
    nav.add_group("Inventario", Icons.INVENTORY)
    nav.add_section("Almacenes", Icons.WAREHOUSE)
    nav.add_section("Ajustes", Icons.ADJUSTMENT)
    nav.item(2).setFlags(nav.item(2).flags() & ~Qt.ItemIsEnabled)
    nav.add_group("Otro grupo", Icons.SETTINGS)
    nav.add_section("Apariencia", Icons.THEME)
    nav.set_collapsed(True)
    nav.select(1)
    destinations = []
    nav.navigated.connect(destinations.append)
    menu = nav.group_menu(0)
    try:
        menu.popup(QPoint(50, 50))
        app.processEvents()
        actions = menu.actions()
        assert len(actions) == 2
        assert actions[0].isEnabled() and not actions[1].isEnabled()
        before = actions[0].icon().pixmap(24, 24).toImage()
        manager.set_theme("dark", app=app)
        app.processEvents()
        assert menu.isVisible()
        assert actions[0].icon().pixmap(24, 24).toImage() != before
        for action, name in zip(actions, (Icons.WAREHOUSE, Icons.ADJUSTMENT)):
            expected = IconProvider.icon(name)
            for mode in (QIcon.Normal, QIcon.Active, QIcon.Selected, QIcon.Disabled):
                assert action.icon().pixmap(24, 24, mode).toImage() == expected.pixmap(24, 24, mode).toImage()
        actions[0].trigger()
        assert destinations == [1]
        assert nav.currentRow() == 1
    finally:
        menu.close()
        nav.deleteLater()
        app.sendPostedEvents(None, QEvent.DeferredDelete)
