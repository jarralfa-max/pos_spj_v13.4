"""Rentabilidad (§33) por sucursal, producto, categoría, cliente, canal,
pedido o ruta: ingreso neto, costo, merma, costos directos y margen de
contribución. Abajo, el resultado CONTABLE por sucursal."""

from __future__ import annotations

from PyQt5.QtWidgets import QLabel

from frontend.desktop.components.searchable_combo import SearchableComboBox
from frontend.desktop.components.tables import ColumnSpec, StandardTable
from frontend.desktop.modules.finance.pages._page_base import FinancePage, compact_combo


class ProfitabilityPage(FinancePage):
    title = "Rentabilidad"
    subtitle = "Margen de contribución por dimensión del negocio"
    period_filter = True
    columns = [
        ColumnSpec("Elemento"),
        ColumnSpec("Cantidad", "numeric"),
        ColumnSpec("Ingreso neto", "numeric"),
        ColumnSpec("Descuentos", "numeric"),
        ColumnSpec("Costo de venta", "numeric"),
        ColumnSpec("Merma", "numeric"),
        ColumnSpec("Costos directos", "numeric"),
        ColumnSpec("Margen bruto", "numeric"),
        ColumnSpec("Contribución", "numeric"),
        ColumnSpec("% contribución", "numeric"),
    ]

    def _build_filters(self, row) -> None:
        self._dimension = SearchableComboBox(placeholder="Dimensión")
        self._dimension.set_options(self._presenter.profitability_dimensions())
        self._dimension.set_current_id("branch")
        self._dimension.selection_changed.connect(lambda *_: self._on_filter())
        compact_combo(self._dimension, 12)
        row.addWidget(self._dimension)

    def _build_extra(self) -> None:
        label = QLabel("Resultado contable por sucursal", self)
        label.setProperty("role", "muted")
        self._layout.addWidget(label)
        self._branches = StandardTable([
            ColumnSpec("Sucursal", "date"), ColumnSpec("Ingreso neto", "numeric"),
            ColumnSpec("Utilidad bruta", "numeric"), ColumnSpec("Utilidad de operación", "numeric"),
            ColumnSpec("Utilidad neta", "numeric")], self)
        self._branches.setMaximumHeight(160)
        self._layout.addWidget(self._branches)

    def _load(self) -> None:
        date_from, date_to = self.period()
        dimension = self._dimension.current_id() or "branch"
        self.set_table(self._presenter.profitability(dimension, date_from, date_to))
        self._branches.load_rows(self._presenter.branch_results(date_from, date_to).rows)
