"""Safe read-only page shell used until each PROC phase supplies its page.
Mirrors frontend/desktop/modules/losses/pages/placeholder_page.py.
"""

from PyQt5.QtWidgets import QVBoxLayout, QWidget

from frontend.desktop.components.page_header import PageHeader
from frontend.desktop.components.tooltip import apply_tooltip
from frontend.desktop.components.view_states import ViewState, create_state_widget


class MeatProcessingPlaceholderPage(QWidget):
    def __init__(self, *, title: str, subtitle: str, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("meatProcessingPage")
        self.setProperty("viewState", "empty")
        self.setAccessibleName(f"Procesamiento Cárnico — {title}")
        self.setAccessibleDescription(subtitle)
        apply_tooltip(
            self,
            title=title,
            description="Sección informativa; su operación se habilita en la fase funcional correspondiente.",
            help_id=f"meat_processing.{title.lower().replace(' ', '_')}",
        )
        layout = QVBoxLayout(self)
        layout.addWidget(PageHeader(title=title, subtitle=subtitle, parent=self))
        layout.addWidget(create_state_widget(
            ViewState.EMPTY, self,
            message="Esta sección se habilitará en su fase funcional correspondiente.",
        ), stretch=1)

    def ensure_loaded(self) -> None:
        return None
