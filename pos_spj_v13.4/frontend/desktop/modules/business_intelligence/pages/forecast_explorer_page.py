"""ForecastExplorerPage (§14/§24-26, BI-26) — "Forecast": product+branch
search (§20 — search box, never a long list) + horizon input + "Generar
forecast" action, rendering the KPI bar + chart `ForecastExplorerPresenter`
builds from a REAL `DemandPlanningService` run. Reuses the KPI/chart shell
every other BI page already has (`ExecutiveDashboardPage`/
`AnalyticalSectionPage`), adding the product/branch selection this page
needs that the read-only dashboard pages don't.
"""

from __future__ import annotations

from PyQt5.QtWidgets import QFormLayout, QHBoxLayout, QMessageBox, QVBoxLayout, QWidget

from frontend.desktop.components import (
    BranchSearchBox,
    HtmlChartView,
    IntegerInput,
    KPIBar,
    PageHeader,
    ProductSearchBox,
    create_primary_button,
)
from frontend.desktop.modules.business_intelligence.presenters.forecast_explorer_presenter import (
    ForecastUnavailableError,
)


class ForecastExplorerPage(QWidget):
    def __init__(self, presenter, parent=None) -> None:
        super().__init__(parent)
        self.setAccessibleName("Inteligencia de Negocios — Forecast")
        self.setAccessibleDescription("Demanda pronosticada por producto y sucursal.")
        self._presenter = presenter
        self._loaded = False
        self._product_id: str | None = None
        self._branch_id: str | None = None

        root = QVBoxLayout(self)
        root.addWidget(PageHeader(
            title="Forecast", subtitle="Demanda pronosticada por producto y sucursal.",
            parent=self))

        form = QFormLayout()
        self.product = ProductSearchBox(parent=self, provider=self._presenter.search_products)
        self.product.selected.connect(self._select_product)
        form.addRow("Producto", self.product)
        self.branch = BranchSearchBox(parent=self, provider=self._presenter.search_branches)
        self.branch.selected.connect(self._select_branch)
        form.addRow("Sucursal (opcional)", self.branch)
        self.horizon = IntegerInput(self, minimum=0, maximum=365)
        form.addRow("Horizonte (días)", self.horizon)
        root.addLayout(form)

        actions = QHBoxLayout()
        actions.addStretch(1)
        generate = create_primary_button(self, "Generar forecast")
        generate.clicked.connect(self.refresh)
        actions.addWidget(generate)
        root.addLayout(actions)

        self.kpis = KPIBar(cards=[])
        root.addWidget(self.kpis)
        self.chart = HtmlChartView(self)
        root.addWidget(self.chart, stretch=1)

    def _select_product(self, option) -> None:
        self._product_id = option.id
        self.product.set_selected_label(option.label)

    def _select_branch(self, option) -> None:
        self._branch_id = option.id
        self.branch.set_selected_label(option.label)

    def ensure_loaded(self) -> None:
        """Populates the settings-driven default horizon; does NOT
        auto-generate a forecast (there is no product selected yet on first
        navigation, and popping a message box on page load would be poor UX
        — generation is always an explicit user action)."""
        if not self._loaded:
            self.horizon.setValue(self._presenter.default_horizon_days())
            self._loaded = True

    def refresh(self) -> None:
        try:
            cards, chart = self._presenter.forecast(
                product_id=self._product_id, branch_id=self._branch_id,
                horizon_days=self.horizon.value())
        except ForecastUnavailableError as exc:
            QMessageBox.information(self, "Forecast", str(exc))
            return
        except Exception as exc:  # noqa: BLE001 - surface, never crash the page
            QMessageBox.warning(self, "Forecast", str(exc))
            return
        self.kpis.set_cards(cards)
        self.chart.set_chart(chart)
