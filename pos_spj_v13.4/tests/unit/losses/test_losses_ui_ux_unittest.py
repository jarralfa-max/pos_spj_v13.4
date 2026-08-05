"""LOSS-21 desktop UI/UX characterization tests (offscreen-safe)."""

import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QApplication, QLabel

from frontend.desktop.modules.losses.losses_view import LossesView
from frontend.desktop.modules.losses.pages.placeholder_page import LossesPlaceholderPage
from frontend.desktop.modules.losses.widgets.losses_sidebar_widget import LossesSidebarWidget


class LossesUiUxTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_sidebar_exposes_theme_accessibility_tooltips_and_badges(self):
        sidebar = LossesSidebarWidget(
            has_permission=lambda _permission: True,
            badges={"pending_review": 3},
        )
        self.assertEqual(sidebar.property("role"), "nav")
        self.assertTrue(sidebar.accessibleName())
        pending = next(
            sidebar.item(row) for row in range(sidebar.count())
            if sidebar.item(row).data(Qt.UserRole) == "losses_pending"
        )
        self.assertEqual(pending.data(Qt.AccessibleTextRole), "Pendientes, 3 pendientes")
        self.assertTrue(pending.toolTip())
        self.assertTrue(pending.data(Qt.AccessibleDescriptionRole))

    def test_workspace_switches_sidebar_at_responsive_breakpoint(self):
        view = LossesView(
            has_permission=lambda _permission: True,
            page_builder=lambda page_id: QLabel(page_id),
        )
        view.resize(820, 600)
        view.apply_responsive_layout()
        self.assertTrue(view.sidebar.collapsed)
        view.resize(1440, 700)
        view.apply_responsive_layout()
        self.assertFalse(view.sidebar.collapsed)

    def test_placeholder_page_is_identified_and_announces_empty_state(self):
        page = LossesPlaceholderPage(title="Alertas", subtitle="Excepciones críticas")
        self.assertEqual(page.accessibleName(), "Mermas — Alertas")
        self.assertEqual(page.property("viewState"), "empty")
        self.assertTrue(page.toolTip())


if __name__ == "__main__":
    unittest.main()
