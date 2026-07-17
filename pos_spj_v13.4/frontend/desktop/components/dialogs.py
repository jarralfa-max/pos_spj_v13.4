"""Canonical dialogs (FASE DS-3).

StandardDialog + confirmation/destructive/form variants. Spanish buttons, viewport-
safe sizing, initial focus, Escape when safe, theme-aware via `#standardDialog`.
"""

from __future__ import annotations

from PyQt5.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLabel,
    QVBoxLayout,
)

from frontend.desktop.i18n.es_mx import ui
from frontend.desktop.themes.tokens import DialogMetrics, Spacing


class StandardDialog(QDialog):
    """Base dialog: title + content area + a standard button box."""

    def __init__(self, parent=None, *, title: str = "",
                 width: int = DialogMetrics.WIDTH_SM) -> None:
        super().__init__(parent)
        self.setObjectName("standardDialog")
        self.setWindowTitle(title)
        self.setMinimumWidth(width)
        self._root = QVBoxLayout(self)
        self._root.setContentsMargins(DialogMetrics.PADDING, DialogMetrics.PADDING,
                                      DialogMetrics.PADDING, DialogMetrics.PADDING)
        self._root.setSpacing(Spacing.MD)
        if title:
            heading = QLabel(title, self)
            heading.setProperty("role", "dialogTitle")
            self._root.addWidget(heading)

    def content_layout(self) -> QVBoxLayout:
        return self._root

    def add_button_box(self, *, ok_text: str = None, cancel_text: str = None,
                       ok_role=QDialogButtonBox.Ok) -> QDialogButtonBox:
        box = QDialogButtonBox(ok_role | QDialogButtonBox.Cancel, self)
        box.button(ok_role).setText(ok_text or ui("action.accept"))
        box.button(QDialogButtonBox.Cancel).setText(cancel_text or ui("action.cancel"))
        box.accepted.connect(self.accept)
        box.rejected.connect(self.reject)
        self._root.addWidget(box)
        return box


class ConfirmationDialog(StandardDialog):
    def __init__(self, parent=None, *, title: str = "", message: str = "",
                 confirm_text: str | None = None) -> None:
        super().__init__(parent, title=title)
        self._root.addWidget(QLabel(message, self))
        box = self.add_button_box(ok_text=confirm_text or ui("action.confirm"))
        box.button(QDialogButtonBox.Ok).setDefault(True)


class DestructiveConfirmationDialog(StandardDialog):
    """Confirmation for irreversible actions; the confirm button is danger-styled."""

    def __init__(self, parent=None, *, title: str = "", message: str = "",
                 confirm_text: str | None = None) -> None:
        super().__init__(parent, title=title)
        self._root.addWidget(QLabel(message, self))
        box = self.add_button_box(ok_text=confirm_text or ui("action.delete"))
        ok = box.button(QDialogButtonBox.Ok)
        ok.setProperty("variant", "danger")
        ok.setObjectName("standardButton")


class FormDialog(StandardDialog):
    """A dialog wrapping a QFormLayout; subclasses fill ``self.form``."""

    def __init__(self, parent=None, *, title: str = "",
                 width: int = DialogMetrics.WIDTH_MD) -> None:
        super().__init__(parent, title=title, width=width)
        self.form = QFormLayout()
        self.form.setSpacing(Spacing.SM)
        self._root.addLayout(self.form)
