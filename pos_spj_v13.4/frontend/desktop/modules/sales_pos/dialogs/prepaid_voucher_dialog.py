"""PrepaidVoucherDialog — vender un vale prepagado en el ticket (2026-10-03).

El vale entra como una línea más: se cobra con la venta (el dinero entra al
turno) y se activa con su saldo al cobrar. La definición de vale prepagado se
crea en Fidelidad → Vales.
"""

from __future__ import annotations

from decimal import Decimal

from PyQt5.QtWidgets import QComboBox, QLabel

from frontend.desktop.components import FormField, MoneyInput, StandardDialog, StandardForm


class PrepaidVoucherDialog(StandardDialog):
    def __init__(self, presenter, *, sale, parent=None) -> None:
        super().__init__(parent, title="Vender vale prepagado")
        self.setObjectName("posPrepaidVoucherDialog")
        self._presenter = presenter
        self._sale = sale
        self.changed = False

        definiciones = presenter.prepaid_voucher_definitions()
        form = StandardForm(self)
        self._definition = QComboBox(self)
        for d in definiciones:
            self._definition.addItem(f"{d['name']} ({d['code']})", d["id"])
        form.add_field("definition", FormField("Tipo de vale", self._definition, required=True))
        self._amount = MoneyInput(self)
        self._amount.setObjectName("posPrepaidAmount")
        form.add_field("amount", FormField("Monto del vale", self._amount, required=True))
        self.content_layout().addWidget(form)

        aviso = QLabel("Se cobra con la venta y queda listo para usarse al cobrar. "
                       "Comprar un vale no acumula puntos.", self)
        aviso.setProperty("role", "muted")
        aviso.setWordWrap(True)
        self.content_layout().addWidget(aviso)

        self._error = QLabel("", self)
        self._error.setProperty("state", "error")
        self._error.setWordWrap(True)
        self._error.hide()
        self.content_layout().addWidget(self._error)

        box = self.add_button_box(ok_text="Agregar al ticket")
        box.accepted.disconnect()
        box.accepted.connect(self._submit)
        if not definiciones:
            self._show_error("No hay un vale prepagado activo. Créalo en Fidelidad → Vales "
                             "(tipo «Vale prepagado»).")
            self._amount.setEnabled(False)

    def set_amount(self, amount: Decimal) -> None:
        self._amount.set_decimal_value(Decimal(str(amount)))

    def _show_error(self, message: str) -> None:
        self._error.setText(message)
        self._error.show()

    def _submit(self) -> None:
        definicion = self._definition.currentData()
        monto = self._amount.decimal_value()
        if not definicion:
            return
        if monto <= 0:
            self._show_error("Captura el monto del vale.")
            return
        result = self._presenter.sell_prepaid_voucher(
            sale_id=self._sale.id, definition_id=definicion, amount=monto)
        if not result.success:
            self._show_error(result.message)
            return
        self.changed = True
        self.accept()
