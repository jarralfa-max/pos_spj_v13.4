"""Resumen de RRHH — KPIs operativos del día."""

from __future__ import annotations

from frontend.desktop.modules.hr.pages._page_base import HRPage


class OverviewPage(HRPage):
    title = "Resumen de Recursos Humanos"
    subtitle = "Indicadores operativos del día en curso"

    def _load(self) -> None:
        self.set_kpis(self._presenter.overview_kpis())
