"""Safe read-only page shell used until each LOSS phase supplies its page."""

from PyQt5.QtWidgets import QVBoxLayout, QWidget

from frontend.desktop.components.page_header import PageHeader
from frontend.desktop.components.tooltip import apply_tooltip
from frontend.desktop.components.view_states import ViewState, create_state_widget


class LossesPlaceholderPage(QWidget):
    def __init__(self, *, title: str, subtitle: str, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("lossesPage")
        self.setProperty("viewState", "empty")
        self.setAccessibleName(f"Mermas — {title}")
        self.setAccessibleDescription(subtitle)
        apply_tooltip(
            self,
            title=title,
            description="Sección informativa; su operación se habilita en la fase funcional correspondiente.",
            help_id=f"losses.{title.lower().replace(' ', '_')}",
        )
        layout = QVBoxLayout(self)
        layout.addWidget(PageHeader(title=title, subtitle=subtitle, parent=self))
        layout.addWidget(create_state_widget(
            ViewState.EMPTY, self,
            message="Esta sección se habilitará en su fase funcional correspondiente.",
        ), stretch=1)

    def ensure_loaded(self) -> None:
        return None
