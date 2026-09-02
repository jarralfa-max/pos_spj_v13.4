"""WizardPage — shared shape for every InitialSetupWizard step.

`InitialSetupWizard` calls `values()`/`validate()` polymorphically across
all seven pages without knowing which concrete page it's looking at — this
base class is what makes that dispatch possible instead of the wizard shell
special-casing each page by name.
"""
from __future__ import annotations

from PyQt5.QtWidgets import QVBoxLayout, QWidget

from frontend.desktop.components.page_header import PageHeader
from frontend.desktop.themes.tokens import Spacing


class WizardPage(QWidget):
    def __init__(self, parent=None, *, title: str = "", subtitle: str = "") -> None:
        super().__init__(parent)
        self._root = QVBoxLayout(self)
        self._root.setSpacing(Spacing.MD)
        self._header = PageHeader(self, title=title, subtitle=subtitle, compact=True)
        self._root.addWidget(self._header)

    def body_layout(self) -> QVBoxLayout:
        return self._root

    def values(self) -> dict:
        """Field values this page contributes to `ProvisioningViewModel`."""
        return {}

    def validate(self) -> list[str]:
        """Spanish error messages; empty list means the page can proceed."""
        return []

    def on_shown(self) -> None:
        """Called each time the wizard navigates to this page. Override to
        refresh derived state (e.g. confirmation_page reads other pages)."""
