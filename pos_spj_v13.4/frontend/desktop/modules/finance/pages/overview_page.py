"""Resumen financiero — KPIs del mes (hechos contables, sin forecast)."""

from __future__ import annotations

from frontend.desktop.modules.finance.pages._page_base import FinancePage


class OverviewPage(FinancePage):
    title = "Resumen financiero"
    subtitle = "Hechos contables del mes en curso"

    def _load(self) -> None:
        self.set_kpis(self._presenter.overview_kpis())
