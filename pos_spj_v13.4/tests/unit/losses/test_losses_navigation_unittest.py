"""Stdlib verification for LOSS-4 when pytest is unavailable."""

import unittest
from pathlib import Path

from backend.application.losses.permissions import LossPermissions
from frontend.desktop.modules.losses.navigation.losses_sidebar import LOSSES_NAV, visible_entries


class LossesNavigationSmokeTest(unittest.TestCase):
    def test_routes_are_unique_permission_aware_and_badged(self):
        self.assertEqual(len(LOSSES_NAV), 16)
        self.assertEqual(len({entry.page_id for entry in LOSSES_NAV}), 16)
        grants = {LossPermissions.OVERVIEW_VIEW, LossPermissions.PENDING_VIEW}
        visible = visible_entries(
            lambda permission: permission in grants,
            {"pending_review": 4},
        )
        self.assertEqual(
            [(entry.page_id, badge) for entry, badge in visible],
            [("losses_overview", None), ("losses_pending", 4)],
        )

    def test_global_navigation_uses_only_mermas(self):
        root = Path(__file__).resolve().parents[3]
        main = (root / "interfaz/main_window.py").read_text(encoding="utf-8")
        menu = (root / "interfaz/menu_lateral.py").read_text(encoding="utf-8")
        self.assertIn('self._conectar("MERMAS",', main)
        self.assertNotIn("ModuloMerma", main)
        self.assertEqual(menu.count('self._crear_boton("Mermas", "MERMAS")'), 1)


if __name__ == "__main__":
    unittest.main()
