"""Alta de dirección de un cliente, con el componente estándar.

NO EXISTÍA. `AddCustomerAddressUseCase` estaba completo —permisos, auditoría,
evento en outbox, dirección predeterminada por tipo— y no tenía ningún llamador:
la ficha del cliente enseñaba la pestaña "Direcciones" como una tabla de sólo
lectura, sin forma de agregar ninguna.

Sólo presentación: el diálogo recoge el `StructuredAddress` del componente, el
tipo y si es la predeterminada; el presentador ejecuta el caso de uso.
"""

from __future__ import annotations

from PyQt5.QtWidgets import QCheckBox

from frontend.desktop.components.address_input import AddressInput
from frontend.desktop.components.dialogs import FormDialog
from frontend.desktop.components.searchable_combo import SearchableComboBox
from frontend.desktop.themes.tokens import DialogMetrics

#: Los tipos del dominio (`backend.domain.customers.enums.AddressType`) con su
#: etiqueta visible. Entrega primero: es el uso más frecuente en esta tienda.
ADDRESS_TYPES = (
    ("DELIVERY", "Entrega"),
    ("FISCAL", "Fiscal"),
    ("BILLING", "Facturación"),
    ("COMMERCIAL", "Comercial"),
    ("PERSONAL", "Personal"),
)


class CustomerAddressDialog(FormDialog):
    def __init__(self, parent=None, *, search_service=None, runner=None) -> None:
        super().__init__(parent, title="Nueva dirección", width=DialogMetrics.WIDTH_LG)
        self._type = SearchableComboBox(self, placeholder="Tipo de dirección")
        self._type.set_options(list(ADDRESS_TYPES))
        self._type.set_current_id("DELIVERY")
        self.address = AddressInput(self, search_service=search_service, runner=runner,
                                    with_references=True)
        self._default = QCheckBox("Usar como predeterminada para este tipo", self)
        self.form.addRow("Tipo *", self._type)
        self.form.addRow("Dirección *", self.address)
        self.form.addRow("", self._default)
        self.add_button_box(ok_text="Guardar")

    def error(self) -> str | None:
        if not self._type.current_id():
            return "Elige el tipo de dirección."
        if not self.address.value().street:
            return "La calle es obligatoria."
        return None

    def values(self) -> dict:
        return {"address": self.address.value(),
                "address_type": str(self._type.current_id() or "DELIVERY"),
                "is_default": self._default.isChecked()}

    def accept(self) -> None:
        # Validar ANTES de cerrar: un diálogo que se cierra y luego avisa del
        # error obliga a capturar todo otra vez.
        problema = self.error()
        if problema:
            from PyQt5.QtWidgets import QMessageBox
            QMessageBox.warning(self, "Dirección", problema)
            return
        super().accept()
