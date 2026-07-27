"""Instrumentos comerciales — vista financiera y de conciliación.

Esta pantalla NO administra cupones, puntos ni campañas (eso es del módulo
propietario). Muestra obligaciones contables, movimientos reconocidos,
perfiles contables y excepciones de integración.
"""

from __future__ import annotations

from frontend.desktop.components.tables import ColumnSpec, StandardTable
from frontend.desktop.modules.finance.pages._page_base import FinancePage


class CommercialInstrumentsPage(FinancePage):
    title = "Instrumentos comerciales"
    subtitle = "Obligaciones contables, conciliación y perfiles (solo reconocimiento financiero)"
    columns = [
        ColumnSpec("Instrumento"),
        ColumnSpec("Referencia", "date"),
        ColumnSpec("Reconocido", "numeric"),
        ColumnSpec("Canjeado", "numeric"),
        ColumnSpec("Pendiente", "numeric"),
        ColumnSpec("Estado", "status"),
        ColumnSpec("Vence", "date"),
    ]

    def _build_extra(self) -> None:
        self._summary = StandardTable(
            [ColumnSpec("Instrumento"), ColumnSpec("Cantidad", "numeric"),
             ColumnSpec("Reconocido", "numeric"), ColumnSpec("Canjeado", "numeric"),
             ColumnSpec("Liberado", "numeric"), ColumnSpec("Pendiente", "numeric")],
            self)
        self._summary.setMaximumHeight(200)
        self._layout.addWidget(self._summary)
        self._exceptions = StandardTable(
            [ColumnSpec("Evento sin asiento"), ColumnSpec("Id", "date"),
             ColumnSpec("Procesado", "date")], self)
        self._exceptions.setMaximumHeight(150)
        self._layout.addWidget(self._exceptions)

    def _load(self) -> None:
        self.set_table(self._presenter.commercial_obligations())
        summary = self._presenter.instrument_summary()
        self._summary.load_rows(summary.rows)
        exceptions = self._presenter.integration_exceptions()
        self._exceptions.load_rows(exceptions.rows)
