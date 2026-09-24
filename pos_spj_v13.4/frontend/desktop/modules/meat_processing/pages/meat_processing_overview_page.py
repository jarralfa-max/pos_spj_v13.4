"""Resumen de Procesamiento Cárnico: qué está esperando a alguien y qué salió.

La pantalla no cuenta nada (§ "la UI no calcula KPIs"): pinta lo que el
presenter le entrega. Los cinco indicadores son los mismos contadores del
sidebar, así que el badge y el Resumen nunca pueden decir números distintos.
"""

from __future__ import annotations

from PyQt5.QtWidgets import QLabel

from frontend.desktop.components.kpi_bar import KPIBar
from frontend.desktop.components.pages import StandardPage
from frontend.desktop.components.tables import ColumnSpec, StandardTable

STATUS_COLUMNS = [
    ColumnSpec("Estado", "status"), ColumnSpec("Órdenes", "numeric"),
    ColumnSpec("Del total", "numeric"),
]

PRODUCTION_COLUMNS = [
    ColumnSpec("Tipo de salida", "status"), ColumnSpec("Salidas", "numeric"),
    ColumnSpec("Cantidad", "numeric"), ColumnSpec("Peso", "numeric"),
]

_SIN_ORDENES = "Esta sucursal todavía no tiene órdenes de procesamiento."


class MeatProcessingOverviewPage(StandardPage):
    def __init__(self, presenter, *, title: str, subtitle: str, parent=None) -> None:
        super().__init__(parent, title=title, subtitle=subtitle)
        self._presenter = presenter
        self._loaded = False
        self.title = title
        self.setAccessibleName(title)
        self.setAccessibleDescription(subtitle)

        self.kpis = KPIBar(cards=[])
        self.add_content(self.kpis)

        self.add_content(self._titulo("Órdenes por estado"))
        self.status_table = StandardTable(STATUS_COLUMNS, self.content)
        self.add_content(self.status_table, 1)

        self.period = QLabel("", self.content)
        self.period.setProperty("role", "muted")
        self.period.setWordWrap(True)
        self.add_content(self._titulo("Producción del periodo"))
        self.add_content(self.period)
        self.production_table = StandardTable(PRODUCTION_COLUMNS, self.content)
        self.add_content(self.production_table, 1)

    def _titulo(self, texto: str) -> QLabel:
        etiqueta = QLabel(texto, self.content)
        etiqueta.setProperty("role", "sectionTitle")
        return etiqueta

    def ensure_loaded(self) -> None:
        if self._loaded:
            return
        self._loaded = True
        self.refresh()

    def refresh(self) -> None:
        modelo = self._presenter.overview()
        self.kpis.set_cards(modelo.kpis)
        self.status_table.load_rows(modelo.by_status.rows, row_ids=modelo.by_status.row_ids)
        self.production_table.load_rows(
            modelo.production.rows, row_ids=modelo.production.row_ids)
        self.period.setText(modelo.period if modelo.by_status.rows else _SIN_ORDENES)
