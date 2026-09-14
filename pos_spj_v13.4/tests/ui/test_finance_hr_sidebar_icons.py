"""Exercise real module navigation while replacing only business page bodies."""
from importlib import import_module

import pytest
from PyQt5.QtCore import QEvent
from PyQt5.QtWidgets import QWidget

from frontend.desktop.components.icons import IconProvider, Icons
from frontend.desktop.themes.theme_manager import ThemeManager


class PageBody(QWidget):
    def __init__(self, presenter, parent=None):
        super().__init__(parent)
        self.loads = 0

    def ensure_loaded(self):
        self.loads += 1


@pytest.mark.parametrize("module_name,view_name,examples", [
    ("finance", "FinanceView", {"Resumen financiero": Icons.DASHBOARD,
                               "Plan de cuentas": Icons.CATALOG, "Asientos": Icons.EDIT}),
    ("hr", "HRView", {"Resumen": Icons.DASHBOARD, "Empleados": Icons.USERS,
                     "Jornadas": Icons.CHECKLIST}),
])
@pytest.mark.parametrize("theme", ["light", "dark"])
def test_module_sidebar_keeps_semantic_icons_and_page_destinations(
        qt_font_resources, monkeypatch, module_name, view_name, examples, theme):
    manager = ThemeManager()
    monkeypatch.setattr(ThemeManager, "_instance", manager)
    manager.apply(qt_font_resources, theme)
    module = import_module(f"frontend.desktop.modules.{module_name}.{module_name}_view")
    definitions = module._NAVIGATION
    monkeypatch.setattr(module, "_NAVIGATION", [
        (*entry[:2], PageBody, *entry[3:]) for entry in definitions])
    view = getattr(module, view_name)(object())
    try:
        nav = view._nav
        destinations = {str(nav.item(row).data(nav._BASE_LABEL_ROLE)): row
                        for row in view._row_to_page_index}
        assert list(destinations) == [entry[1] for entry in definitions]
        for label, icon in examples.items():
            assert nav.item(destinations[label]).data(nav._ICON_ROLE) == icon
        identifiers = [nav.item(row).data(nav._ICON_ROLE) for row in destinations.values()]
        assert Icons.HOME not in identifiers
        assert len(set(identifiers)) > 1
        for row in destinations.values():
            nav.select(row)
            assert view._stack.currentIndex() == view._row_to_page_index[row]
            assert view._stack.currentWidget().loads > 0
        nav.set_collapsed(True)
        manager.set_theme("dark" if theme == "light" else "light", app=qt_font_resources)
        for row in range(nav.count()):
            item = nav.item(row)
            icon = item.data(nav._ICON_ROLE)
            assert icon and icon != Icons.HOME
            assert item.icon().pixmap(24, 24).toImage() == IconProvider.icon(icon).pixmap(24, 24).toImage()
            if item.data(nav._GROUP_ROLE):
                menu = nav.group_menu(row)
                try:
                    if menu.actions():
                        menu.actions()[0].trigger()
                        assert view._stack.currentIndex() == view._row_to_page_index[row + 1]
                finally:
                    menu.deleteLater()
        nav.set_collapsed(False)
        assert list(destinations) == [str(nav.item(row).data(nav._BASE_LABEL_ROLE))
                                      for row in destinations.values()]
    finally:
        view.deleteLater()
        qt_font_resources.sendPostedEvents(None, QEvent.DeferredDelete)
