"""PricingScenarioPage (§14/§41-45, BI-29) — "Escenarios": product+branch
search + a signed price-change % input + "Simular" action, rendering the
KPI bar `PricingScenarioPresenter` builds from a REAL `PricingWhatIfService`
run (never saves the simulated price — §42: a what-if never writes).
"""

from __future__ import annotations

from PyQt5.QtWidgets import QFormLayout, QHBoxLayout, QMessageBox, QVBoxLayout, QWidget

from frontend.desktop.components import (
    BranchSearchBox,
    KPIBar,
    NumericInput,
    PageHeader,
    ProductSearchBox,
    create_primary_button,
)
from frontend.desktop.modules.business_intelligence.presenters.pricing_scenario_presenter import (
    ScenarioUnavailableError,
    map_scenario_kpis,
)


class PricingScenarioPage(QWidget):
    def __init__(self, presenter, parent=None) -> None:
        super().__init__(parent)
        self.setAccessibleName("Inteligencia de Negocios — Escenarios")
        self.setAccessibleDescription(
            "Simulaciones what-if de precio, demanda y compras.")
        self._presenter = presenter
        self._loaded = False
        self._product_id: str | None = None
        self._branch_id: str | None = None

        root = QVBoxLayout(self)
        root.addWidget(PageHeader(
            title="Escenarios",
            subtitle="Simulaciones what-if de precio, demanda y compras.",
            parent=self))

        form = QFormLayout()
        self.product = ProductSearchBox(parent=self, provider=self._presenter.search_products)
        self.product.selected.connect(self._select_product)
        form.addRow("Producto", self.product)
        self.branch = BranchSearchBox(parent=self, provider=self._presenter.search_branches)
        self.branch.selected.connect(self._select_branch)
        form.addRow("Sucursal", self.branch)
        self.price_change_pct = NumericInput(self, decimals=1, minimum=-50.0, maximum=50.0)
        form.addRow("Cambio de precio (%)", self.price_change_pct)
        root.addLayout(form)

        actions = QHBoxLayout()
        actions.addStretch(1)
        simulate = create_primary_button(self, "Simular")
        simulate.clicked.connect(self.refresh)
        actions.addWidget(simulate)
        root.addLayout(actions)

        self.kpis = KPIBar(cards=[])
        root.addWidget(self.kpis)

    def _select_product(self, option) -> None:
        self._product_id = option.id
        self.product.set_selected_label(option.label)

    def _select_branch(self, option) -> None:
        self._branch_id = option.id
        self.branch.set_selected_label(option.label)

    def ensure_loaded(self) -> None:
        if not self._loaded:
            self._loaded = True

    def refresh(self) -> None:
        try:
            result = self._presenter.simulate(
                product_id=self._product_id, branch_id=self._branch_id,
                price_change_pct=self.price_change_pct.value())
        except ScenarioUnavailableError as exc:
            QMessageBox.information(self, "Escenarios", str(exc))
            return
        except Exception as exc:  # noqa: BLE001 - surface, never crash the page
            QMessageBox.warning(self, "Escenarios", str(exc))
            return
        self.kpis.set_cards(map_scenario_kpis(result))
