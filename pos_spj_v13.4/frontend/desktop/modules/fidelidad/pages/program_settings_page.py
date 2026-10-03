"""ProgramSettingsPage (ruta ``fidelidad.settings``) — reglas del programa de
puntos, editables desde Fidelidad (decisión del usuario, 2026-10-02).

Acumulación: pesos por punto, si lo pagado a crédito acumula, meses de
vigencia (0 = no caducan). Canje: valor de un punto, mínimo para canjear y tope
del ticket pagadero con puntos. La página sólo captura; valida y guarda
`UpdateLoyaltyProgramSettingsUseCase` (permiso `GROWTH_ENGINE.configuracion.
editar`), que deja el antes/después en la auditoría de Fidelidad.

La ruta ya existía en la navegación y mostraba un estado vacío: ni los ajustes
de canje tenían pantalla.
"""

from __future__ import annotations

from decimal import Decimal

from PyQt5.QtWidgets import QLabel, QVBoxLayout, QWidget

from frontend.desktop.components import (
    DecimalInput,
    FormField,
    IntegerInput,
    PercentInput,
    StandardForm,
    create_primary_button,
)
from frontend.desktop.components.selection_controls import StandardCheckBox
from frontend.desktop.components.pages import StandardPage
from frontend.desktop.themes.tokens import Spacing


class ProgramSettingsPage(StandardPage):
    def __init__(self, presenter, parent=None) -> None:
        super().__init__(parent, title="Configuración", subtitle="Reglas de acumulación, canje y caducidad.")
        self.setObjectName("fidelidadProgramSettingsPage")
        self._presenter = presenter

        layout = self.content_layout
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(Spacing.MD)

        acumulacion = QLabel("ACUMULACIÓN", self)
        acumulacion.setProperty("role", "sectionTitle")
        layout.addWidget(acumulacion)
        form = StandardForm(self)
        self.pesos_per_point = DecimalInput(self, precision=2, minimum="0.01")
        form.add_field("pesos_per_point", FormField(
            "Pesos por punto", self.pesos_per_point, required=True,
            helper="Cada cuántos pesos del total pagado gana el cliente 1 punto"))
        self.credit_earns = StandardCheckBox("Las ventas a crédito también acumulan", self)
        form.add_field("credit_earns", FormField("Crédito", self.credit_earns))
        self.expiration_months = IntegerInput(self, minimum=0, maximum=120)
        form.add_field("expiration_months", FormField(
            "Vigencia (meses)", self.expiration_months,
            helper="0 = los puntos no caducan. Caduca primero lo más antiguo."))
        layout.addWidget(form)

        canje = QLabel("CANJE", self)
        canje.setProperty("role", "sectionTitle")
        layout.addWidget(canje)
        form2 = StandardForm(self)
        self.point_value = DecimalInput(self, precision=2, minimum="0.01")
        form2.add_field("point_value", FormField(
            "Valor de un punto ($)", self.point_value, required=True))
        self.min_points = IntegerInput(self, minimum=0, maximum=1000000)
        form2.add_field("min_points", FormField(
            "Mínimo para canjear (puntos)", self.min_points))
        self.max_percent = PercentInput(self)
        form2.add_field("max_percent", FormField(
            "Tope del ticket pagadero con puntos", self.max_percent))
        layout.addWidget(form2)

        self._status = QLabel("", self)
        self._status.setWordWrap(True)
        self._status.hide()
        layout.addWidget(self._status)

        self.btn_save = create_primary_button(self, "Guardar ajustes")
        self.btn_save.clicked.connect(self.save)
        layout.addWidget(self.btn_save)
        layout.addStretch(1)

        self.ensure_loaded()

    def ensure_loaded(self) -> None:
        settings = self._presenter.program_settings()
        editable = self._presenter.can_edit_settings()
        for widget in (self.pesos_per_point, self.credit_earns, self.expiration_months,
                       self.point_value, self.min_points, self.max_percent, self.btn_save):
            widget.setEnabled(editable)
        if not editable:
            self._show("Sólo lectura: necesitas el permiso de configuración de Fidelidad.",
                       error=False)
        if settings is None:
            return
        self.pesos_per_point.set_decimal(settings.accrual.pesos_per_point)
        self.credit_earns.setChecked(settings.accrual.credit_earns)
        self.expiration_months.setValue(int(settings.accrual.expiration_months))
        self.point_value.set_decimal(settings.redemption.point_value)
        self.min_points.setValue(int(settings.redemption.min_points))
        self.max_percent.set_decimal_value(settings.redemption.max_percent * Decimal("100"))

    def save(self) -> None:
        result = self._presenter.save_program_settings(
            pesos_per_point=self.pesos_per_point.decimal_value() or Decimal("0"),
            credit_earns=self.credit_earns.isChecked(),
            expiration_months=int(self.expiration_months.value()),
            point_value=self.point_value.decimal_value() or Decimal("0"),
            min_points=int(self.min_points.value()),
            max_percent=self.max_percent.decimal_value() / Decimal("100"))
        if result.success:
            self._show("Ajustes guardados. Aplican desde la siguiente venta.", error=False)
        else:
            self._show(result.message, error=True)

    def _show(self, message: str, *, error: bool) -> None:
        self._status.setProperty("state", "error" if error else "success")
        self._status.setText(message)
        self._status.show()
