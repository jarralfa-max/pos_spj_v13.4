"""Configuración de Cárnico (Fase 10, 2026-09-19) — tolerancias de rendimiento.

Decisión del usuario: una tolerancia GLOBAL, igual para todos los cortes. Se
comparan contra la diferencia de cada corte respecto a lo esperado del despiece:
aviso ≤ tolerancia ≤ crítico. Fuera de tolerancia, ejecutar la orden exige la
autorización de otro usuario y abre un caso en Mermas.

Sólo presentación: guarda por el presenter → caso de uso (permiso
`PRODUCCION.configuracion.editar`).
"""

from __future__ import annotations

from PyQt5.QtWidgets import QFormLayout, QLabel, QMessageBox, QVBoxLayout, QWidget

from frontend.desktop.components import DecimalInput, PageHeader, create_primary_button
from frontend.desktop.themes.tokens import Spacing


class MeatProcessingSettingsPage(QWidget):
    def __init__(self, presenter, *, title: str, subtitle: str, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("meatProcessingSettingsPage")
        self._presenter = presenter
        self.title = title

        layout = QVBoxLayout(self)
        layout.setContentsMargins(Spacing.LG, Spacing.MD, Spacing.LG, Spacing.MD)
        layout.setSpacing(Spacing.MD)
        self.header = PageHeader(title=title, subtitle=subtitle, compact=True)
        layout.addWidget(self.header)

        ayuda = QLabel(
            "Tolerancias de rendimiento (%) sobre la diferencia de cada corte contra lo "
            "esperado de su despiece. Debe cumplirse aviso ≤ tolerancia ≤ crítico.", self)
        ayuda.setWordWrap(True)
        layout.addWidget(ayuda)

        form = QFormLayout()
        self.warning = DecimalInput(self, precision=2, minimum="0", suffix="%")
        self.tolerance = DecimalInput(self, precision=2, minimum="0", suffix="%")
        self.critical = DecimalInput(self, precision=2, minimum="0", suffix="%")
        form.addRow("Aviso:", self.warning)
        form.addRow("Tolerancia:", self.tolerance)
        form.addRow("Crítico:", self.critical)
        layout.addLayout(form)

        self.save_button = create_primary_button(text="Guardar tolerancias")
        self.save_button.clicked.connect(self._on_save)
        layout.addWidget(self.save_button)
        layout.addStretch(1)

    def ensure_loaded(self) -> None:
        self.refresh()

    def refresh(self) -> None:
        valores = self._presenter.yield_tolerances() or {}
        for campo, clave in ((self.warning, "warning_pct"), (self.tolerance, "tolerance_pct"),
                             (self.critical, "critical_pct")):
            if valores.get(clave) is not None:
                campo.set_decimal(valores[clave])

    def _on_save(self) -> None:
        ok, mensaje = self._presenter.save_yield_tolerances(
            warning_pct=self.warning.decimal_value(),
            tolerance_pct=self.tolerance.decimal_value(),
            critical_pct=self.critical.decimal_value())
        (QMessageBox.information if ok else QMessageBox.warning)(self, "Configuración", mensaje)
        if ok:
            self.refresh()
