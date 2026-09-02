"""FidelidadOverviewPage (LOY-25) — the Fidelidad dashboard: simple KPI
counts drawn straight from the presenter's already-authorized lists.

UI only — "la UI no calcula KPIs" (§90): every number here is `len()` of a
list the presenter already returned, never a recomputed business metric.
"""

from __future__ import annotations

from PyQt5.QtWidgets import QLabel, QVBoxLayout, QWidget

from frontend.desktop.components import KPIBar, KPIDTO
from frontend.desktop.themes.tokens import Spacing


class FidelidadOverviewPage(QWidget):
    def __init__(self, presenter, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("fidelidadOverviewPage")
        self._presenter = presenter
        self._loaded = False

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(Spacing.MD)

        self._status = QLabel("", self)
        self._status.setObjectName("fidelidadOverviewStatus")
        self._status.setProperty("state", "LOADING")
        self._status.setWordWrap(True)
        self._status.hide()
        layout.addWidget(self._status)

        self._kpi_bar = KPIBar(cards=[])
        layout.addWidget(self._kpi_bar)
        layout.addStretch(1)

    def ensure_loaded(self) -> None:
        if not self._loaded:
            self.reload()

    def reload(self) -> None:
        self._status.setText("Cargando indicadores…")
        self._status.setProperty("state", "LOADING")
        self._status.show()
        try:
            programs = self._presenter.list_programs()
            campaigns = self._presenter.list_sweepstakes_campaigns()
            self._kpi_bar.set_cards([
                KPIDTO(key="active_programs", title="Programas activos",
                      value=str(len(programs)), variant="primary"),
                KPIDTO(key="active_sweepstakes", title="Sorteos activos",
                      value=str(len(campaigns)), variant="primary"),
            ])
            self._loaded = True
            self._status.hide()
        except Exception as exc:  # a page must always show *something*
            self._status.setProperty("state", "ERROR")
            self._status.setText(f"No fue posible cargar el resumen: {exc}")
