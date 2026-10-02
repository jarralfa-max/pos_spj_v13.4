"""RedeemPointsDialog — canjear puntos del cliente en la venta (§38-41).

Muestra lo que Fidelidad permite (saldo, mínimo, tope del ticket y valor del
punto, de `SalesLoyaltyClient.preview_redemption`) y captura cuántos puntos
usar. No calcula nada: el caso de uso vuelve a previsualizar y canjea lo que
sale de ahí, y su motivo se muestra si lo rechaza.
"""

from __future__ import annotations

from decimal import Decimal

from PyQt5.QtWidgets import QLabel

from frontend.desktop.components import FormField, IntegerInput, StandardDialog, StandardForm


class RedeemPointsDialog(StandardDialog):
    def __init__(self, presenter, *, sale, preview: dict, parent=None) -> None:
        super().__init__(parent, title="Canjear puntos")
        self.setObjectName("posRedeemPointsDialog")
        self._presenter = presenter
        self._sale = sale
        self.result_message = ""

        maximo = int(preview.get("puntos_maximos_canjeables") or 0)
        minimo = int(preview.get("min_puntos_canje") or 0)
        valor = Decimal(str(preview.get("valor_por_punto") or 0))
        resumen = QLabel(
            f"Disponibles: {int(preview.get('puntos_disponibles') or 0)} puntos  ·  "
            f"1 punto = ${valor:,.2f}\n"
            f"Máximo en esta venta: {maximo} puntos (${Decimal(str(preview.get('descuento_maximo') or 0)):,.2f})"
            + (f"  ·  mínimo {minimo}" if minimo else ""), self)
        resumen.setWordWrap(True)
        self.content_layout().addWidget(resumen)

        form = StandardForm(self)
        self._points = IntegerInput(self, minimum=0, maximum=max(maximo, 0))
        self._points.setValue(maximo)
        form.add_field("points", FormField("Puntos a canjear", self._points, required=True))
        self.content_layout().addWidget(form)

        self._equivale = QLabel("", self)
        self._equivale.setProperty("role", "muted")
        self.content_layout().addWidget(self._equivale)
        self._valor = valor
        self._points.valueChanged.connect(self._update_equivalence)
        self._update_equivalence()

        self._error = QLabel("", self)
        self._error.setProperty("state", "error")
        self._error.setWordWrap(True)
        self._error.hide()
        self.content_layout().addWidget(self._error)

        box = self.add_button_box(ok_text="Canjear")
        box.accepted.disconnect()
        box.accepted.connect(self._submit)
        if maximo <= 0:
            self._show_error(preview.get("mensaje") or
                             "El cliente no alcanza el mínimo para canjear en esta venta.")
            self._points.setEnabled(False)

    def set_points(self, value: int) -> None:
        self._points.setValue(int(value))

    def _update_equivalence(self) -> None:
        self._equivale.setText(f"Descuento: ${self._points.value() * self._valor:,.2f}")

    def _show_error(self, message: str) -> None:
        self._error.setText(message)
        self._error.show()

    def _submit(self) -> None:
        puntos = int(self._points.value())
        if puntos <= 0:
            self._show_error("Indica cuántos puntos canjear.")
            return
        result = self._presenter.redeem_loyalty_points(sale_id=self._sale.id, points=puntos)
        if not result.success:
            self._show_error(result.message)
            return
        self.result_message = result.message
        self.accept()
