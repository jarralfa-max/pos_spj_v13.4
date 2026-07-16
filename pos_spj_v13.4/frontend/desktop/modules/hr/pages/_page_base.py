"""Shared page scaffolding for the HR module.

Pages only render widgets, capture input and delegate to the presenter.
No SQL, no business rules, no inline colors (theme QSS owns the look).
"""

from __future__ import annotations

from PyQt5.QtWidgets import QMessageBox, QVBoxLayout, QWidget

from frontend.desktop.components.tables import ColumnSpec, StandardTable
from frontend.desktop.modules.hr.hr_view_models import TableViewModel
from modulos.ui_components import PageHeader, create_kpi_bar, create_secondary_button


class HRPage(QWidget):
    """Base page: PageHeader + optional KPI bar + StandardTable + refresh."""

    title: str = ""
    subtitle: str = ""
    columns: list[ColumnSpec] = []

    def __init__(self, presenter, parent=None) -> None:
        super().__init__(parent)
        self._presenter = presenter
        self._loaded = False
        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(16, 16, 16, 16)
        self._layout.setSpacing(12)

        self.header = PageHeader(self, title=self.title, subtitle=self.subtitle)
        refresh = create_secondary_button(self, "Actualizar")
        refresh.clicked.connect(self.reload)
        self.header.add_action(refresh)
        self._build_actions()
        self._layout.addWidget(self.header)

        self._kpi_container: QWidget | None = None
        if self.columns:
            self.table = StandardTable(self.columns, self)
            self._layout.addWidget(self.table, stretch=1)
        self._build_extra()

    # hooks -----------------------------------------------------------------
    def _build_actions(self) -> None:
        """Add page-specific header actions (override)."""

    def _build_extra(self) -> None:
        """Add page-specific widgets under the table (override)."""

    def _load(self) -> None:
        """Fetch data through the presenter and fill widgets (override)."""

    # lifecycle ---------------------------------------------------------------
    def ensure_loaded(self) -> None:
        if not self._loaded:
            self.reload()

    def reload(self) -> None:
        try:
            self._load()
            self._loaded = True
        except Exception as exc:  # surface errors; never swallow silently
            QMessageBox.warning(self, "Recursos Humanos",
                                f"No fue posible cargar la vista:\n{exc}")

    # helpers -----------------------------------------------------------------
    def set_table(self, model: TableViewModel) -> None:
        self.table.load_rows(model.rows, row_ids=model.row_ids)

    def selected_id(self) -> str | None:
        return self.table.selected_row_id() if self.columns else None

    def set_kpis(self, kpis) -> None:
        if self._kpi_container is not None:
            self._layout.removeWidget(self._kpi_container)
            self._kpi_container.deleteLater()
        items = [{"title": kpi.title, "value": kpi.value, "tone": kpi.variant}
                 for kpi in kpis]
        self._kpi_container = create_kpi_bar(self, items)
        self._layout.insertWidget(1, self._kpi_container)

    def notify(self, ok: bool, message: str) -> None:
        if ok:
            QMessageBox.information(self, "Recursos Humanos", message)
            self.reload()
        else:
            QMessageBox.warning(self, "Recursos Humanos", message)
