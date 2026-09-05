"""ReportsPage (§14/§30, BI-30) — "Reportes": pick a report from the
catalog + a format, a native save-file dialog, then export via the REAL
`BiExportService` — a real file lands on disk, this page performs a real
export, not a placeholder.
"""

from __future__ import annotations

from PyQt5.QtWidgets import QComboBox, QFileDialog, QHBoxLayout, QMessageBox, QVBoxLayout, QWidget

from frontend.desktop.components import PageHeader, create_primary_button
from frontend.desktop.modules.business_intelligence.presenters.reports_presenter import (
    ReportUnavailableError,
)
from frontend.desktop.themes.tokens import TouchTarget

_FORMAT_LABELS = (("xlsx", "Excel (.xlsx)"), ("pdf", "PDF (.pdf)"), ("csv", "CSV (.csv)"))
_FORMAT_FILTERS = {"xlsx": "Excel (*.xlsx)", "pdf": "PDF (*.pdf)", "csv": "CSV (*.csv)"}


class ReportsPage(QWidget):
    def __init__(self, presenter, parent=None) -> None:
        super().__init__(parent)
        self.setAccessibleName("Inteligencia de Negocios — Reportes")
        self.setAccessibleDescription("Biblioteca de reportes exportables.")
        self._presenter = presenter
        self._loaded = False

        root = QVBoxLayout(self)
        root.addWidget(PageHeader(
            title="Reportes", subtitle="Biblioteca de reportes exportables.", parent=self))

        self.report_selector = QComboBox(self)
        self.report_selector.setMinimumHeight(TouchTarget.MIN_HEIGHT)
        self.report_selector.setAccessibleName("Reporte")
        for report in self._presenter.list_reports():
            self.report_selector.addItem(report["title"], report["key"])
        root.addWidget(self.report_selector)

        self.format_selector = QComboBox(self)
        self.format_selector.setMinimumHeight(TouchTarget.MIN_HEIGHT)
        self.format_selector.setAccessibleName("Formato")
        for fmt, label in _FORMAT_LABELS:
            self.format_selector.addItem(label, fmt)
        root.addWidget(self.format_selector)

        actions = QHBoxLayout()
        actions.addStretch(1)
        export = create_primary_button(self, "Exportar")
        export.clicked.connect(self.export_selected)
        actions.addWidget(export)
        root.addLayout(actions)

    def ensure_loaded(self) -> None:
        self._loaded = True

    def export_selected(self) -> None:
        report_key = self.report_selector.currentData()
        fmt = self.format_selector.currentData()
        suggested = self._presenter.default_filename(report_key, fmt)
        filepath, _ = QFileDialog.getSaveFileName(
            self, "Guardar reporte", suggested, _FORMAT_FILTERS[fmt])
        if not filepath:
            return
        try:
            written = self._presenter.generate(report_key=report_key, fmt=fmt, filepath=filepath)
        except ReportUnavailableError as exc:
            QMessageBox.warning(self, "Reportes", str(exc))
            return
        QMessageBox.information(self, "Reportes", f"Archivo guardado en:\n{written}")
