"""Evaluaciones de desempeño — vista base (módulo en preparación).

No hay lógica de negocio aquí: la evaluación de desempeño se incorporará como
un caso de uso propio del contexto RRHH. Esta pantalla presenta el estado
actual sin ejecutar SQL ni cálculos.
"""

from __future__ import annotations

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QLabel

from frontend.desktop.modules.hr.pages._page_base import HRPage


class EvaluationsPage(HRPage):
    title = "Evaluaciones de desempeño"
    subtitle = "Seguimiento de desempeño del personal"

    def _build_extra(self) -> None:
        message = QLabel(
            "Las evaluaciones de desempeño se habilitarán como un caso de uso "
            "dedicado del contexto de Recursos Humanos.\n\n"
            "Los datos de asistencia, puntualidad y horas extra ya alimentan los "
            "indicadores del resumen y estarán disponibles como insumo objetivo.")
        message.setObjectName("hrEmptyState")
        message.setWordWrap(True)
        message.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        self._layout.addWidget(message, stretch=1)

    def _load(self) -> None:  # nothing to fetch yet
        return
