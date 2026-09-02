"""ModuleErrorView — SHELL-13.

What `ApplicationWindow` shows in `ContentHost` when `ModuleLoader.ensure_loaded()`
fails for the module backing the route just navigated to. Built on the
existing design-system `StateWidget`/`ViewState.ERROR` (FASE DS-3) rather
than a bespoke error screen, plus a "Reintentar" button — retrying is the
whole point of `ModuleLoader` treating `FAILED` as retryable, not a dead
end.
"""
from __future__ import annotations

from typing import Callable, Optional

from PyQt5.QtWidgets import QVBoxLayout, QWidget

from frontend.desktop.components.buttons import create_primary_button
from frontend.desktop.components.view_states import ViewState, create_state_widget
from frontend.desktop.themes.tokens import Spacing


class ModuleErrorView(QWidget):
    def __init__(
        self, module_id: str, error: BaseException, parent=None,
        *, on_retry: Optional[Callable[[], None]] = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("moduleErrorView")
        self.module_id = module_id
        self.error = error

        message = f"El módulo '{module_id}' no pudo cargarse.\n{error}"
        state_widget = create_state_widget(ViewState.ERROR, self, message=message)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(Spacing.XL, Spacing.XL, Spacing.XL, Spacing.XL)
        layout.setSpacing(Spacing.MD)
        layout.addWidget(state_widget, 1)

        if on_retry is not None:
            retry_button = create_primary_button(self, text="Reintentar")
            retry_button.clicked.connect(on_retry)
            layout.addWidget(retry_button, 0)
            self.retry_button = retry_button
        else:
            self.retry_button = None


def build_module_error_view(
    module_id: str, error: BaseException, parent=None, *, on_retry: Optional[Callable[[], None]] = None,
) -> ModuleErrorView:
    return ModuleErrorView(module_id, error, parent, on_retry=on_retry)
