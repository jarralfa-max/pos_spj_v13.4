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
        # Auditoría RRHH HR-30: estar en la navegación no implica que exista el
        # proceso. No hay ciclos, objetivos, participantes ni aprobación.
        message = QLabel(
            "No disponible en esta versión.\n\n"
            "Las evaluaciones de desempeño aún no tienen ciclos, objetivos, "
            "participantes ni aprobación. Mientras tanto, la puntualidad, las "
            "horas extra y las ausencias se consultan en Asistencia y en el Resumen.")
        message.setObjectName("hrEmptyState")
        message.setWordWrap(True)
        message.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        self._layout.addWidget(message, stretch=1)

    def _load(self) -> None:  # nothing to fetch yet
        return
