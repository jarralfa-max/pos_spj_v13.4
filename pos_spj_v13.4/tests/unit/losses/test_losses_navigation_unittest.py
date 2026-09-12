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

    def test_global_navigation_has_exactly_one_losses_entry(self):
        """Antes leía `interfaz/main_window.py` y `menu_lateral.py` buscando la
        forma del shell anterior (`self._conectar("MERMAS", ...)`). Los dos
        archivos se borraron en la reconstrucción, así que la prueba llevaba
        fallando con `FileNotFoundError` — un fallo que no dice nada de Mermas.

        Lo que protegía sigue importando y se comprueba contra el menú vivo:
        dos entradas al mismo módulo confunden sin fallar, porque las dos
        abren algo.
        """
        from frontend.desktop.shell.sidebar.migrated_modules_navigation import (
            MIGRATED_MODULES_NAVIGATION_ITEMS,
        )

        entradas = [i for i in MIGRATED_MODULES_NAVIGATION_ITEMS
                    if i.module_id == "losses"]
        self.assertEqual(len(entradas), 1)
        self.assertEqual(entradas[0].item_id, "nav.losses")


if __name__ == "__main__":
    unittest.main()
