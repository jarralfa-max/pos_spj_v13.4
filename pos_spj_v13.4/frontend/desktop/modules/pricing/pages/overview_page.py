"""Pricing overview page (PRC-7) — KPI bar of price/cost health.

UI only: all values come from the presenter. No SQL, no business logic, no local
styles.
"""

from __future__ import annotations

from PyQt5.QtWidgets import QVBoxLayout, QWidget

from frontend.desktop.components import KPIBar, KPIDTO, PageHeader
from frontend.desktop.components.icons import Icons
from frontend.desktop.themes.tokens import Spacing


class PricingOverviewPage(QWidget):
    def __init__(self, presenter, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("pricingOverviewPage")
        self._presenter = presenter

        layout = QVBoxLayout(self)
        layout.setContentsMargins(Spacing.LG, Spacing.MD, Spacing.LG, Spacing.MD)
        layout.setSpacing(Spacing.MD)

        self.header = PageHeader(
            title="Resumen de Precios y Costos",
            subtitle="Listas, precios por producto, costos y precios bajo mínimo.",
            icon=getattr(Icons, "PRICE", None), compact=True)
        layout.addWidget(self.header)

        self.kpi_bar = KPIBar()
        layout.addWidget(self.kpi_bar)
        layout.addStretch(1)
        self.refresh()

    def refresh(self) -> None:
        self.kpi_bar.set_cards([
            KPIDTO(key=k.key, title=k.title, value=k.value, variant=k.variant,
                   subtitle=k.subtitle)
            for k in self._presenter.overview_kpis()])
