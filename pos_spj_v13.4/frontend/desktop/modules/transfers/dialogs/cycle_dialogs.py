"""Diálogos del ciclo de una transferencia (integración Logística 32cfbf):
rechazar, despachar con verificador independiente y recibir por renglón.
Validan antes de cerrar; las reglas (segregación, saldos) las aplica el caso de uso."""

from __future__ import annotations

from decimal import Decimal

from PyQt5.QtWidgets import QLabel

from frontend.desktop.components import (
    DecimalInput,
    FormDialog,
    PasswordInput,
    StandardCheckBox,
    StandardLineEdit,
)


class _Dialog(FormDialog):
    def __init__(self, parent=None, *, title: str, ok_text: str, width: int = 560) -> None:
        super().__init__(parent, title=title, width=width)
        self._error = QLabel("", self)
        self._error.setObjectName("textDanger")
        self._error.setWordWrap(True)
        self._ok_text = ok_text

    def _finish(self) -> None:
        self.form.addRow(self._error)
        self.add_button_box(ok_text=self._ok_text, on_accept=self._accept_if_valid)

    def problem(self) -> str | None:
        return None

    def _accept_if_valid(self) -> None:
        problema = self.problem()
        self._error.setText(problema or "")
        if problema is None:
            self.accept()


class RejectTransferDialog(_Dialog):
    def __init__(self, parent=None, *, number: str) -> None:
        super().__init__(parent, title=f"Rechazar {number}", ok_text="Rechazar")
        self.reason = StandardLineEdit(self, placeholder="Motivo (obligatorio)")
        self.form.addRow("Motivo:", self.reason)
        self._finish()

    def problem(self) -> str | None:
        return None if self.reason.text().strip() else "Captura el motivo del rechazo."


class DispatchTransferDialog(_Dialog):
    """El embarque exige que OTRA persona verifique la carga (usuario y clave)."""

    def __init__(self, parent=None, *, detail: dict, verify) -> None:
        super().__init__(parent, title=f"Despachar {detail['number']}", ok_text="Despachar")
        self._verify = verify
        self.verifier_user_id: str | None = None
        resumen = ", ".join(f"{l['product_name']} {l['picked']}" for l in detail["lines"]
                            if Decimal(str(l["picked"])) > 0)
        self.form.addRow(QLabel(f"Se despacha lo surtido: {resumen}", self))
        self.user = StandardLineEdit(self, placeholder="Usuario de quien verifica la carga")
        self.password = PasswordInput(self, placeholder="Clave de quien verifica")
        self.seal = StandardLineEdit(self, placeholder="Sello (opcional)")
        self.vehicle = StandardLineEdit(self, placeholder="Vehículo (opcional)")
        self.temperature = DecimalInput(self, precision=1, nullable=True, suffix="°C")
        self._cold = bool(detail.get("cold_chain"))
        self.form.addRow("Verifica:", self.user)
        self.form.addRow("Clave:", self.password)
        self.form.addRow("Sello:", self.seal)
        self.form.addRow("Vehículo:", self.vehicle)
        if self._cold:
            self.form.addRow("Temperatura:", self.temperature)
        self._finish()

    def problem(self) -> str | None:
        if self._cold and self.temperature.decimal_value() is None:
            return "Cadena de frío: captura la temperatura al despachar."
        user_id, problema = self._verify(self.user.text().strip(), self.password.value())
        if user_id is None:
            return problema or "Usuario o clave del verificador incorrectos."
        self.verifier_user_id = user_id
        return None


class ReceiveTransferDialog(_Dialog):
    """Por renglón pendiente: cuánto llegó y si se acepta. Lo que no llegó queda
    como diferencia; lo rechazado entra en cuarentena."""

    def __init__(self, parent=None, *, detail: dict, shipment: dict) -> None:
        super().__init__(parent, title=f"Recibir {detail['number']} · {shipment['number']}",
                         ok_text="Confirmar recepción", width=640)
        self._campos: dict[str, tuple[DecimalInput, StandardCheckBox, Decimal]] = {}
        for linea in shipment["pending_lines"]:
            cantidad = DecimalInput(self, precision=3, minimum="0", nullable=True)
            cantidad.setPlaceholderText(f"Pendiente {linea['pending']}")
            aceptado = StandardCheckBox("Aceptar", self)
            aceptado.setChecked(True)
            self._campos[linea["line_id"]] = (cantidad, aceptado, Decimal(str(linea["pending"])))
            self.form.addRow(f"{linea['product_name']} (pendiente {linea['pending']}):", cantidad)
            self.form.addRow("", aceptado)
        self._finish()

    def lines(self) -> list[dict]:
        return [{"line_id": lid, "quantity": c.decimal_value() or Decimal("0"),
                 "accepted": a.isChecked()} for lid, (c, a, _p) in self._campos.items()
                if c.decimal_value() is not None]

    def problem(self) -> str | None:
        if not self.lines():
            return "Captura cuánto llegó de al menos un producto (0 si no llegó nada)."
        for lid, (cantidad, _a, pendiente) in self._campos.items():
            valor = cantidad.decimal_value()
            if valor is not None and valor > pendiente:
                return f"No se puede recibir más de lo pendiente ({pendiente})."
        return None
