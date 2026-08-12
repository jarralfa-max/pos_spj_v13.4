"""PROC-4 desktop UI/UX characterization tests (offscreen-safe). Mirrors
tests/unit/losses/test_losses_ui_ux_unittest.py.
"""

import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QApplication, QLabel

from frontend.desktop.modules.meat_processing.meat_processing_view import MeatProcessingView
from frontend.desktop.modules.meat_processing.navigation.meat_processing_sidebar import (
    SLAUGHTER_FEATURE_FLAG,
)
from frontend.desktop.modules.meat_processing.pages.placeholder_page import (
    MeatProcessingPlaceholderPage,
)
from frontend.desktop.modules.meat_processing.widgets.meat_processing_sidebar_widget import (
    MeatProcessingSidebarWidget,
)


class MeatProcessingUiUxTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_sidebar_exposes_theme_accessibility_tooltips_and_badges(self):
        sidebar = MeatProcessingSidebarWidget(
            has_permission=lambda _permission: True,
            badges={"orders_needing_attention": 3},
        )
        self.assertEqual(sidebar.property("role"), "nav")
        self.assertTrue(sidebar.accessibleName())
        orders = next(
            sidebar.item(row) for row in range(sidebar.count())
            if sidebar.item(row).data(Qt.UserRole) == "mp_processing_orders"
        )
        self.assertEqual(orders.data(Qt.AccessibleTextRole), "Órdenes, 3 pendientes")
        self.assertTrue(orders.toolTip())
        self.assertTrue(orders.data(Qt.AccessibleDescriptionRole))

    def test_sidebar_hides_slaughter_sections_without_the_feature_flag(self):
        sidebar = MeatProcessingSidebarWidget(has_permission=lambda _permission: True)
        page_ids = {sidebar.item(row).data(Qt.UserRole) for row in range(sidebar.count())}
        self.assertNotIn("mp_animal_reception", page_ids)

    def test_sidebar_shows_slaughter_sections_once_the_feature_flag_is_enabled(self):
        sidebar = MeatProcessingSidebarWidget(
            has_permission=lambda _permission: True,
            has_feature=lambda flag: flag == SLAUGHTER_FEATURE_FLAG,
        )
        page_ids = {sidebar.item(row).data(Qt.UserRole) for row in range(sidebar.count())}
        self.assertIn("mp_animal_reception", page_ids)

    def test_workspace_switches_sidebar_at_responsive_breakpoint(self):
        view = MeatProcessingView(
            has_permission=lambda _permission: True,
            page_builder=lambda page_id: QLabel(page_id),
        )
        view.resize(820, 600)
        view.apply_responsive_layout()
        self.assertTrue(view.sidebar.collapsed)
        view.resize(1440, 700)
        view.apply_responsive_layout()
        self.assertFalse(view.sidebar.collapsed)

    def test_workspace_routes_to_the_first_visible_entry_on_load(self):
        view = MeatProcessingView(
            has_permission=lambda _permission: True,
            page_builder=lambda page_id: QLabel(page_id),
        )
        self.assertEqual(view.active_route, "mp_overview")

    def test_placeholder_page_is_identified_and_announces_empty_state(self):
        page = MeatProcessingPlaceholderPage(title="Alertas", subtitle="Excepciones críticas")
        self.assertEqual(page.accessibleName(), "Procesamiento Cárnico — Alertas")
        self.assertEqual(page.property("viewState"), "empty")
        self.assertTrue(page.toolTip())


if __name__ == "__main__":
    unittest.main()
