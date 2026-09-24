"""Trazabilidad de Procesamiento Cárnico: de qué salió un lote y a dónde fue.

Se elige un lote PRODUCIDO por la sucursal (los de Rendimientos → Por corte) y la
pantalla enseña sus dos mitades: los lotes de entrada que consumió la orden, y los
movimientos aguas abajo que reporta Inventario, dueño de la genealogía de lotes.
"""

from __future__ import annotations

from PyQt5.QtWidgets import QLabel

from frontend.desktop.components.pages import StandardPage
from frontend.desktop.components.search_selector import SearchSelector
from frontend.desktop.components.tables import ColumnSpec, StandardTable

INPUT_COLUMNS = [
    ColumnSpec("Lote de entrada"), ColumnSpec("Insumo"), ColumnSpec("Peso", "numeric"),
]

CHAINED_COLUMNS = [
    ColumnSpec("Orden"), ColumnSpec("Proceso", "status"), ColumnSpec("Insumo"),
    ColumnSpec("Peso", "numeric"), ColumnSpec("Encadenado", "date"),
]

DESTINATION_COLUMNS = [
    ColumnSpec("Fecha", "date"), ColumnSpec("Movimiento", "status"), ColumnSpec("Módulo"),
    ColumnSpec("Documento"), ColumnSpec("Sucursal"), ColumnSpec("Peso", "numeric"),
]

_SIN_LOTE = "Elige un lote producido para ver su recorrido."


class MeatTraceabilityPage(StandardPage):
    def __init__(self, presenter, *, title: str, subtitle: str, parent=None) -> None:
        super().__init__(parent, title=title, subtitle=subtitle)
        self._presenter = presenter
        self.title = title
        self.setAccessibleName(title)
        self.setAccessibleDescription(subtitle)

        self.lot = SearchSelector(
            parent=self.content, provider=presenter.search_lots,
            placeholder="Buscar lote producido (código o producto)…")
        self.lot.selected.connect(self._lot_selected)
        self.add_content(self.lot)

        self.summary = QLabel(_SIN_LOTE, self.content)
        self.summary.setWordWrap(True)
        self.add_content(self.summary)
        self.origin = QLabel("", self.content)
        self.origin.setWordWrap(True)
        self.origin.setProperty("role", "muted")
        self.add_content(self.origin)

        self.add_content(self._titulo("De qué salió"))
        self.inputs_table = StandardTable(INPUT_COLUMNS, self.content)
        self.add_content(self.inputs_table, 1)

        self.add_content(self._titulo("Se consumió en otra orden"))
        self.chained_table = StandardTable(CHAINED_COLUMNS, self.content)
        self.add_content(self.chained_table, 1)

        self.add_content(self._titulo("A dónde fue"))
        self.destinations_table = StandardTable(DESTINATION_COLUMNS, self.content)
        self.add_content(self.destinations_table, 1)

    def _titulo(self, texto: str) -> QLabel:
        etiqueta = QLabel(texto, self.content)
        etiqueta.setProperty("role", "sectionTitle")
        return etiqueta

    def ensure_loaded(self) -> None:
        """Nada que cargar: el recorrido empieza cuando se elige un lote."""

    def _lot_selected(self, option) -> None:
        self.show_lot(option.id if option is not None else "")

    def show_lot(self, lot_id: str) -> None:
        modelo = self._presenter.trace(lot_id)
        self.summary.setText(modelo.summary or _SIN_LOTE)
        self.origin.setText(modelo.origin)
        self.inputs_table.load_rows(modelo.inputs.rows, row_ids=modelo.inputs.row_ids)
        self.chained_table.load_rows(modelo.chained.rows, row_ids=modelo.chained.row_ids)
        self.destinations_table.load_rows(
            modelo.destinations.rows, row_ids=modelo.destinations.row_ids)
