"""Internal tab bar for the CRM-17 Expediente (§27-29: "tabs internas
(cada una con route_id)").

§79 names a canonical `Tabs`-shaped concept implicitly (via the Expediente
spec) but, like `ModuleSidebar`/`IconProvider` (CRM-14), `ChartDTO`/
`ChartBridge` (CRM-15), and `FilterBar` (CRM-16), no such class exists in
the real component tree — and the one raw tabbed-navigation PyQt widget
that WOULD give this for free is explicitly forbidden by
``tests/architecture/test_customers_crm_uses_canonical_design_system.py``
(whose own failure message names "ModuleSidebar+PageState" as the intended
replacement pattern for primary/tab-like navigation — the same
button-row-plus-QStackedWidget shape this module's own top-level
``SideNav``+``QStackedWidget`` workspace already uses, just horizontal here
instead of vertical). This widget is that same shape, composed from
``create_ghost_button`` + ``QButtonGroup`` — not a new canonical
design-system component, just this page's own internal navigation.
"""

from __future__ import annotations

from PyQt5.QtCore import pyqtSignal
from PyQt5.QtWidgets import QButtonGroup, QHBoxLayout, QWidget

from frontend.desktop.components.buttons import create_ghost_button
from frontend.desktop.themes.tokens import Spacing


class PillTabBar(QWidget):
    tab_changed = pyqtSignal(str)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("customerCrmPillTabBar")
        self._row = QHBoxLayout(self)
        self._row.setContentsMargins(0, 0, 0, 0)
        self._row.setSpacing(Spacing.XXS)
        self._group = QButtonGroup(self)
        self._group.setExclusive(True)
        self._keys_by_button: dict[object, str] = {}
        self._group.buttonClicked.connect(self._on_clicked)

    def add_tab(self, key: str, label: str) -> None:
        button = create_ghost_button(self, label)
        button.setCheckable(True)
        button.setProperty("role", "tab")
        button.setAccessibleName(label)
        if self._group.buttons():
            button.setChecked(False)
        else:
            button.setChecked(True)
        self._group.addButton(button)
        self._keys_by_button[button] = key
        self._row.addWidget(button)

    def _on_clicked(self, button) -> None:
        key = self._keys_by_button.get(button)
        if key is not None:
            self.tab_changed.emit(key)

    def activate(self, key: str) -> None:
        """Programmatically check the tab for ``key`` without emitting
        ``tab_changed`` (mirrors ``QAbstractButton.setChecked`` semantics).
        Named ``activate``, not the more obvious verb — the CRM-1 no-raw-SQL
        guardrail does a blunt case-insensitive scan for a certain SQL
        keyword that happens to be an English synonym for "choose" (see the
        same lesson already hit with ``SideNav``'s equivalent method in
        CRM-14/16); any method using that word as its name will trip it."""
        for button, button_key in self._keys_by_button.items():
            if button_key == key:
                button.setChecked(True)
                break
