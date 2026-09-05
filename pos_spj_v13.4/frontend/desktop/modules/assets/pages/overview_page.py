"""AssetsOverviewPage (ASSET-17, §91) — the Activos dashboard: KPIs + alerts.

UI only: every number comes from ``presenter.dashboard()`` (backed by
``AssetDashboardQueryService``, ASSET-14's own read service) — "La UI no
calcula KPI" (§91). This page never counts, filters, or decides what counts
as out-of-service; it only renders what the presenter hands it. Only the 5
KPIs the backend actually computes today are shown (total/available/
in_maintenance/out_of_service/disposal_pending) — §91 names six ("Valor de
adquisición", "Costo mantenimiento del periodo") that need a financial
projection query service this phase doesn't build; inventing numbers the
backend doesn't provide would violate the same "la UI no calcula KPIs" rule
this page exists to respect.
"""

from __future__ import annotations

from PyQt5.QtWidgets import QFrame, QHBoxLayout, QLabel, QVBoxLayout, QWidget

from frontend.desktop.components import AlertCard, DashboardGrid, KPIBar, KPIDTO
from frontend.desktop.themes.tokens import Spacing


class _AlertsBar(QFrame):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("assetsOverviewAlertsBar")
        self._row = QHBoxLayout(self)
        self._row.setContentsMargins(0, 0, 0, 0)
        self._row.setSpacing(Spacing.SM)

    def set_alerts(self, alerts: list[tuple[str, str]]) -> None:
        while self._row.count():
            item = self._row.takeAt(0)
            if item.widget() is not None:
                item.widget().deleteLater()
        for variant, message in alerts:
            card = AlertCard(self, variant=variant)
            label = QLabel(message, card)
            label.setWordWrap(True)
            card.add(label)
            self._row.addWidget(card, stretch=1)
        self.setVisible(bool(alerts))


class AssetsOverviewPage(QWidget):
    def __init__(self, presenter, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("assetsOverviewPage")
        self._presenter = presenter
        self._loaded = False

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(Spacing.MD)

        self._status = QLabel("", self)
        self._status.setObjectName("assetsOverviewStatus")
        self._status.setProperty("state", "LOADING")
        self._status.setWordWrap(True)
        self._status.hide()
        layout.addWidget(self._status)

        self._alerts_bar = _AlertsBar(self)
        layout.addWidget(self._alerts_bar)

        self._grid = DashboardGrid(self)
        self._kpi_bar = KPIBar(cards=[])
        self._grid.add_kpi_bar(self._kpi_bar)
        self._grid.add_stretch()
        layout.addWidget(self._grid, stretch=1)

    def ensure_loaded(self) -> None:
        if not self._loaded:
            self.reload()

    def reload(self) -> None:
        self._status.setText("Cargando indicadores…")
        self._status.setProperty("state", "LOADING")
        self._status.show()
        try:
            view = self._presenter.dashboard()
            self._kpi_bar.set_cards(self._build_kpis(view))
            self._alerts_bar.set_alerts(self._build_alerts(view))
            self._loaded = True
            self._status.hide()
        except Exception as exc:  # a page must always show *something*
            self._status.setProperty("state", "ERROR")
            self._status.setText(f"No fue posible cargar el resumen: {exc}")

    @staticmethod
    def _build_kpis(view) -> list[KPIDTO]:
        return [
            KPIDTO(key="total_assets", title="Total de activos",
                  value=str(view.total_assets), variant="primary"),
            KPIDTO(key="available", title="Disponibles",
                  value=str(view.available), variant="success"),
            KPIDTO(key="in_maintenance", title="En mantenimiento",
                  value=str(view.in_maintenance), variant="primary"),
            KPIDTO(key="out_of_service", title="Fuera de servicio",
                  value=str(view.out_of_service),
                  variant="danger" if view.out_of_service else "success"),
            KPIDTO(key="disposal_pending", title="Pendientes de baja",
                  value=str(view.disposal_pending),
                  variant="danger" if view.disposal_pending else "success"),
        ]

    @staticmethod
    def _build_alerts(view) -> list[tuple[str, str]]:
        alerts: list[tuple[str, str]] = []
        if view.out_of_service:
            alerts.append(("danger", f"{view.out_of_service} activo(s) fuera de servicio"))
        if view.disposal_pending:
            alerts.append(("danger", f"{view.disposal_pending} activo(s) pendiente(s) de baja"))
        return alerts
