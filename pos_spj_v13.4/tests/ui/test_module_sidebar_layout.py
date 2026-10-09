"""Operational sidebars share Pricing's rail geometry and manual collapse."""
from importlib import import_module

import pytest
from PyQt5.QtCore import QEvent, Qt
from PyQt5.QtTest import QTest

from frontend.desktop.components.side_nav import SideNav
from frontend.desktop.themes.theme_manager import ThemeManager
from frontend.desktop.themes.tokens import density_metrics
from tests.ui.test_operational_sidebar_icons import SIDEBARS, assert_icon


@pytest.fixture
def manager(qt_font_resources, monkeypatch):
    instance = ThemeManager()
    monkeypatch.setattr(ThemeManager, "_instance", instance)
    yield instance
    qt_font_resources.sendPostedEvents(None, QEvent.DeferredDelete)


@pytest.mark.parametrize("module,class_name", SIDEBARS)
@pytest.mark.parametrize("theme", ("light", "dark"))
@pytest.mark.parametrize("density", ("compact", "comfortable", "touch"))
def test_sidebar_matches_pricing_and_collapse_preserves_navigation(
    manager, qt_font_resources, module, class_name, theme, density,
):
    manager.apply(qt_font_resources, theme, density=density)
    root = f"frontend.desktop.modules.{module}"
    navigation = import_module(f"{root}.navigation.{module}_sidebar")
    sidebar_class = getattr(import_module(f"{root}.widgets.{module}_sidebar_widget"), class_name)
    entries = navigation.visible_entries(lambda _permission: True)
    badges = {entry.badge_key: 3 for entry, _ in entries if entry.badge_key}
    expected = navigation.visible_entries(lambda _permission: True, badges)
    sidebar = sidebar_class(has_permission=lambda _permission: True, badges=badges)
    reference = SideNav()
    reference.setProperty("role", "nav")
    for entry, badge in expected:
        reference.add_section(entry.title if badge is None else f"{entry.title} ({badge})", entry.icon)
    routes = []
    sidebar.route_requested.connect(routes.append)
    try:
        sidebar.resize(240, 768)
        reference.resize(240, 768)
        sidebar.show()
        reference.show()
        qt_font_resources.processEvents()
        assert sidebar.property("role") == "nav"
        assert (sidebar.minimumWidth(), sidebar.maximumWidth()) == (180, 240)
        assert sidebar.viewport().geometry() == reference.viewport().geometry()
        assert sidebar._toggle.isVisible()
        assert sidebar.rect().contains(sidebar._toggle.geometry())
        assert not sidebar._toggle.icon().isNull()
        assert "Contraer" in sidebar._toggle.toolTip()
        sidebar.setCurrentRow(1)
        assert routes == [expected[1][0].page_id]
        original = [sidebar.item(row).text() for row in range(sidebar.count())]

        for collapsed in (True, False):
            QTest.mouseClick(sidebar._toggle, Qt.LeftButton)
            reference.set_collapsed(collapsed)
            qt_font_resources.processEvents()
            assert sidebar.collapsed is collapsed
            assert (sidebar.minimumWidth(), sidebar.maximumWidth()) == (
                reference.minimumWidth(), reference.maximumWidth(),
            )
            assert sidebar.viewport().geometry() == reference.viewport().geometry()
            assert sidebar.rect().contains(sidebar._toggle.geometry())
            assert ("Expandir" if collapsed else "Contraer") in sidebar._toggle.toolTip()
            assert sidebar.currentRow() == 1
            assert routes == [expected[1][0].page_id]
            for row, (entry, _badge) in enumerate(expected):
                item = sidebar.item(row)
                assert item.data(Qt.UserRole) == entry.page_id
                assert item.toolTip() == entry.tooltip
                assert item.data(Qt.AccessibleTextRole)
                assert item.text() == ("" if collapsed else original[row])
                assert item.sizeHint().height() == density_metrics(density).sidebar_item_height
                assert_icon(item, entry.icon)

        sidebar.setCurrentRow(2)
        assert routes == [expected[1][0].page_id, expected[2][0].page_id]
    finally:
        sidebar.close()
        reference.close()
        sidebar.deleteLater()
        reference.deleteLater()
