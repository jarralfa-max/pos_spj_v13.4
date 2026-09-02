"""OrdersOverviewPage (ORD-28) — the "Resumen" landing page: KPI bar fed by
the REAL ORD-27 analytics/badge query services, no placeholder content."""

from __future__ import annotations

from PyQt5.QtWidgets import QHBoxLayout, QMessageBox, QVBoxLayout, QWidget

from frontend.desktop.components import KPIBar, PageHeader, create_secondary_button


class OrdersOverviewPage(QWidget):
    def __init__(self, presenter, parent=None) -> None:
        super().__init__(parent)
        self.setAccessibleName("Resumen de Pedidos y Delivery")
        self._presenter = presenter
        self._loaded = False

        root = QVBoxLayout(self)
        root.addWidget(PageHeader(
            title="Resumen", subtitle="Indicadores operativos de pedidos y entregas.",
            parent=self))
        actions = QHBoxLayout()
        actions.addStretch(1)
        refresh = create_secondary_button(self, "Actualizar")
        refresh.clicked.connect(self.refresh)
        actions.addWidget(refresh)
        root.addLayout(actions)
        self.kpis = KPIBar(cards=[])
        root.addWidget(self.kpis)
        root.addStretch(1)

    def ensure_loaded(self) -> None:
        if not self._loaded:
            self.refresh()
            self._loaded = True

    def refresh(self) -> None:
        try:
            cards = self._presenter.kpi_cards()
        except Exception as exc:  # noqa: BLE001 - surface, never crash the page
            QMessageBox.warning(self, "Resumen", str(exc))
            return
        self.kpis.set_cards(cards)
