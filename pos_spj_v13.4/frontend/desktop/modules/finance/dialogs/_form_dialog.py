"""Base form dialog for the finance module (StandardDialog policy)."""

from __future__ import annotations

from frontend.desktop.components.dialogs import FormDialog


class FinanceFormDialog(FormDialog):
    dialog_title = ""

    def __init__(self, parent=None) -> None:
        super().__init__(parent, title=self.dialog_title)
        self._build_form()
        self.add_button_box(on_accept=self._accept_if_valid)

    def _build_form(self) -> None:
        raise NotImplementedError

    def _is_valid(self) -> bool:
        return True

    def _accept_if_valid(self) -> None:
        if self._is_valid():
            self.accept()
