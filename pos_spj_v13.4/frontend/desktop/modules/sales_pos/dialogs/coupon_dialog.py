"""CouponDialog — aplicar o retirar cupones del ticket (2026-10-03).

Captura el código (o lo recibe del lector) y lo manda tal cual: Fidelidad
decide si aplica y por cuánto (vigencia, dueño, combinación con puntos u otros
cupones). La pantalla no calcula nada; si se rechaza muestra el motivo.
"""

from __future__ import annotations

from PyQt5.QtWidgets import QLabel, QListWidget, QListWidgetItem

from frontend.desktop.components import (
    FormField,
    StandardDialog,
    StandardForm,
    StandardLineEdit,
    create_danger_button,
)


class CouponDialog(StandardDialog):
    def __init__(self, presenter, *, sale, parent=None) -> None:
        super().__init__(parent, title="Cupones")
        self.setObjectName("posCouponDialog")
        self._presenter = presenter
        self._sale = sale
        self.changed = False

        self._applied = QListWidget(self)
        self._applied.setObjectName("posCouponApplied")
        self.content_layout().addWidget(QLabel("Aplicados a esta venta:", self))
        self.content_layout().addWidget(self._applied)
        self._btn_remove = create_danger_button(self, "Quitar cupón seleccionado")
        self._btn_remove.clicked.connect(self._remove_selected)
        self.content_layout().addWidget(self._btn_remove)

        form = StandardForm(self)
        self._code = StandardLineEdit(self, placeholder="Código del cupón")
        self._code.setObjectName("posCouponCode")
        form.add_field("code", FormField("Código", self._code, required=True))
        self.content_layout().addWidget(form)

        self._error = QLabel("", self)
        self._error.setProperty("state", "error")
        self._error.setWordWrap(True)
        self._error.hide()
        self.content_layout().addWidget(self._error)

        box = self.add_button_box(ok_text="Aplicar cupón", cancel_text="Cerrar")
        box.accepted.disconnect()
        box.accepted.connect(self._submit)
        self._render()

    def set_code(self, code: str) -> None:
        self._code.setText(code)

    def _render(self) -> None:
        self._applied.clear()
        for cupon in getattr(self._sale, "coupons", ()) or ():
            item = QListWidgetItem(f"{cupon['code']}: -${cupon['amount']:,.2f}")
            item.setData(256, cupon["coupon_instance_id"])
            self._applied.addItem(item)
        self._btn_remove.setEnabled(self._applied.count() > 0)

    def _show_error(self, message: str) -> None:
        self._error.setText(message)
        self._error.show()

    def _apply_result(self, result) -> bool:
        if not result.success:
            self._show_error(result.message)
            return False
        self._error.hide()
        self.changed = True
        self._sale = result.data.get("sale") or self._presenter.get_sale(self._sale.id)
        self._render()
        return True

    def _remove_selected(self) -> None:
        item = self._applied.currentItem()
        if item is None:
            return
        self._apply_result(self._presenter.remove_coupon(
            sale_id=self._sale.id, coupon_instance_id=item.data(256)))

    def _submit(self) -> None:
        code = self._code.value() if hasattr(self._code, "value") else self._code.text().strip()
        if not code:
            self._show_error("Captura el código del cupón.")
            return
        if self._apply_result(self._presenter.apply_coupon(sale_id=self._sale.id, code=code)):
            self._code.setText("")
