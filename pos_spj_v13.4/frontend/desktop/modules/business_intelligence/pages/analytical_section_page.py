"""AnalyticalSectionPage (§14, BI-25) — generic page for a single BI section
("Ventas"/"Inventario"/"Compras"/"Finanzas"): KPI bar + charts + tables, fed
by `AnalyticalSectionPresenter`. Mirrors `ExecutiveDashboardPage` (BI-24) for
the KPI/chart parts, adding table rendering for the tabular rows
`section_data()` payloads carry that the executive dashboard's own payload
does not.
"""

from __future__ import annotations

from PyQt5.QtWidgets import QHBoxLayout, QLabel, QMessageBox, QVBoxLayout, QWidget

from frontend.desktop.components import (
    ColumnSpec, HtmlChartView, KPIBar, PageHeader, StandardTable, create_secondary_button,
)


class AnalyticalSectionPage(QWidget):
    def __init__(self, presenter, *, title: str, subtitle: str, parent=None) -> None:
        super().__init__(parent)
        self.setAccessibleName(f"Inteligencia de Negocios — {title}")
        self.setAccessibleDescription(subtitle)
        self._presenter = presenter
        self._loaded = False

        root = QVBoxLayout(self)
        root.addWidget(PageHeader(title=title, subtitle=subtitle, parent=self))

        actions = QHBoxLayout()
        actions.addStretch(1)
        refresh = create_secondary_button(self, "Actualizar")
        refresh.clicked.connect(self.refresh)
        actions.addWidget(refresh)
        root.addLayout(actions)

        self.kpis = KPIBar(cards=[])
        root.addWidget(self.kpis)

        self.charts: list[HtmlChartView] = []
        self._charts_layout = QVBoxLayout()
        root.addLayout(self._charts_layout, stretch=1)

        self._tables: list[StandardTable] = []
        self._tables_layout = QVBoxLayout()
        root.addLayout(self._tables_layout)

    def ensure_loaded(self) -> None:
        if not self._loaded:
            self.refresh()
            self._loaded = True

    def refresh(self) -> None:
        try:
            self._presenter.invalidate()
            cards = self._presenter.kpi_cards()
            charts = self._presenter.charts()
            tables = self._presenter.tables()
        except Exception as exc:  # noqa: BLE001 - surface, never crash the page
            QMessageBox.warning(self, "Inteligencia de negocios", str(exc))
            return

        self.kpis.set_cards(cards)

        while len(self.charts) < len(charts):
            view = HtmlChartView(self)
            self.charts.append(view)
            self._charts_layout.addWidget(view, stretch=1)
        for view, dto in zip(self.charts, charts):
            view.set_chart(dto)

        while len(self._tables) < len(tables):
            index = len(self._tables)
            dto = tables[index]
            self._tables_layout.addWidget(QLabel(dto.title, self))
            table = StandardTable([ColumnSpec(c.title, c.kind) for c in dto.columns], self)
            self._tables_layout.addWidget(table)
            self._tables.append(table)
        for table, dto in zip(self._tables, tables):
            table.load_rows([list(row) for row in dto.rows])
