"""Inventory dashboard page (INV-25) — KPI bar + availability snapshot.

UI only: all values come from the presenter. Renders the JUANIS PageHeader, a
KPIBar of replenishment health, and a StandardTable of availability. No SQL, no
business logic.
"""

from __future__ import annotations

from PyQt5.QtWidgets import QVBoxLayout, QWidget

from frontend.desktop.components import (
    ColumnSpec,
    KPIBar,
    KPIDTO,
    PageHeader,
    StandardTable,
)
from frontend.desktop.components.icons import Icons
from frontend.desktop.themes.tokens import Spacing

_VARIANT_STATE = {"danger": "ERROR", "warning": "STALE", "info": "READY"}


class InventoryDashboardPage(QWidget):
    def __init__(self, presenter, product_ids=None, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("inventoryDashboardPage")
        self._presenter = presenter
        self._product_ids = list(product_ids or [])

        layout = QVBoxLayout(self)
        layout.setContentsMargins(Spacing.LG, Spacing.MD, Spacing.LG, Spacing.MD)
        layout.setSpacing(Spacing.MD)

        self.header = PageHeader(
            title="Panel de Inventario",
            subtitle="Existencias, alertas de reposición y salud del stock.",
            icon=getattr(Icons, "INVENTORY", None), compact=True)
        layout.addWidget(self.header)

        self._kpi_bar = KPIBar(cards=[])
        layout.addWidget(self._kpi_bar)

        self._table = StandardTable(columns=[
            ColumnSpec("Producto", "text"),
            ColumnSpec("En mano", "numeric"),
            ColumnSpec("Reservado", "numeric"),
            ColumnSpec("Disponible", "numeric"),
        ])
        layout.addWidget(self._table)

    def refresh(self) -> None:
        kpis = self._presenter.replenishment_kpis()
        self._kpi_bar.set_cards([
            KPIDTO(key=k.key, title=k.title, value=k.value, variant=k.variant,
                   tooltip=k.tooltip) for k in kpis])
        table = self._presenter.availability(product_ids=self._product_ids)
        self._table.load_rows(table.rows, row_ids=table.row_ids)
