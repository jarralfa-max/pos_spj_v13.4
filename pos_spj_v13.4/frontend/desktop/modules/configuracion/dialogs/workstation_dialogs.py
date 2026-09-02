"""Dialogs for the "Estaciones" (General) section — SET-6's domain had
zero UI before this round. Built entirely on `FormDialog` (FASE DS-3),
same shape as `device_dialogs.py` (`Workstation` and `Device` share an
independently-defined identical 5-of-7-state lifecycle).
"""

from __future__ import annotations

from PyQt5.QtWidgets import QCheckBox, QDialogButtonBox

from frontend.desktop.components import (
    FormDialog,
    SearchableComboBox,
    StandardLineEdit,
    StandardTextArea,
    apply_tooltip,
)

_WORKSTATION_TYPES = (
    ("POS", "Punto de venta"), ("BACKOFFICE", "Back office"), ("WAREHOUSE", "Almacén"),
    ("RECEIVING", "Recepción"), ("PRODUCTION", "Producción"), ("PROCESSING", "Procesamiento"),
    ("DELIVERY_COORDINATION", "Coordinación de entregas"), ("CUSTOMER_SERVICE", "Atención a clientes"),
    ("ADMINISTRATION", "Administración"), ("MOBILE", "Móvil"), ("KIOSK_FUTURE", "Kiosco (futuro)"),
)


class WorkstationCreateDialog(FormDialog):
    def __init__(self, parent=None, *, branch_options=()) -> None:
        super().__init__(parent, title="Nueva estación")
        self.branch = SearchableComboBox(self, placeholder="Selecciona una sucursal…")
        self.branch.set_options([(o.entity_id, o.name) for o in branch_options])
        self.branch.setAccessibleName("Sucursal")
        self.form.addRow("Sucursal:", self.branch)

        self.workstation_type = SearchableComboBox(self, placeholder="Selecciona un tipo…")
        self.workstation_type.set_options(_WORKSTATION_TYPES)
        self.workstation_type.setAccessibleName("Tipo de estación")
        self.form.addRow("Tipo:", self.workstation_type)

        self.code = StandardLineEdit(self)
        self.code.setAccessibleName("Código")
        apply_tooltip(self.code, "Identificador corto único. Ej. «POS-01».")
        self.form.addRow("Código:", self.code)

        self.name = StandardLineEdit(self)
        self.name.setAccessibleName("Nombre")
        self.form.addRow("Nombre:", self.name)

        self.device_identifier = StandardLineEdit(self)
        self.device_identifier.setAccessibleName("Identificador de equipo")
        apply_tooltip(self.device_identifier, "Opcional. Número de serie, MAC, hostname, etc.")
        self.form.addRow("Identificador (opcional):", self.device_identifier)

        self.operating_system = StandardLineEdit(self)
        self.operating_system.setAccessibleName("Sistema operativo")
        self.form.addRow("Sistema operativo (opcional):", self.operating_system)

        self.offline_enabled = QCheckBox("Permite operar sin conexión", self)
        self.offline_enabled.setChecked(True)
        self.form.addRow("", self.offline_enabled)

        self.add_button_box(ok_text="Registrar")

    def values(self) -> dict:
        return {
            "branch_id": self.branch.current_id(), "workstation_type": self.workstation_type.current_id(),
            "code": self.code.text().strip(), "name": self.name.text().strip(),
            "device_identifier": self.device_identifier.text().strip(),
            "operating_system": self.operating_system.text().strip(),
            "offline_enabled": self.offline_enabled.isChecked(),
        }


class WorkstationEditDialog(FormDialog):
    def __init__(
        self, parent=None, *, name: str = "", device_identifier: str = "", operating_system: str = "",
    ) -> None:
        super().__init__(parent, title="Editar estación")
        self.name = StandardLineEdit(self)
        self.name.setText(name)
        self.name.setAccessibleName("Nombre")
        self.form.addRow("Nombre:", self.name)

        self.device_identifier = StandardLineEdit(self)
        self.device_identifier.setText(device_identifier)
        self.device_identifier.setAccessibleName("Identificador de equipo")
        self.form.addRow("Identificador (opcional):", self.device_identifier)

        self.operating_system = StandardLineEdit(self)
        self.operating_system.setText(operating_system)
        self.operating_system.setAccessibleName("Sistema operativo")
        self.form.addRow("Sistema operativo (opcional):", self.operating_system)

        self.add_button_box(ok_text="Guardar")

    def values(self) -> dict:
        return {
            "name": self.name.text().strip(),
            "device_identifier": self.device_identifier.text().strip(),
            "operating_system": self.operating_system.text().strip(),
        }


class BlockWorkstationDialog(FormDialog):
    """Blocking a `Workstation` always requires a reason — the domain
    (`Workstation.block`) rejects a blank one. Mirrors
    `device_dialogs.py::BlockDeviceDialog`."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent, title="Bloquear estación")
        self.reason = StandardTextArea(self)
        self.reason.setAccessibleName("Motivo de bloqueo")
        apply_tooltip(self.reason, "Explica por qué se bloquea esta estación.")
        self.form.addRow("Motivo:", self.reason)
        box = self.add_button_box(ok_text="Bloquear")
        self._ok_button = box.button(QDialogButtonBox.Ok)
        self._ok_button.setEnabled(False)
        self.reason.textChanged.connect(self._on_text_changed)

    def _on_text_changed(self) -> None:
        self._ok_button.setEnabled(bool(self.reason_text()))

    def reason_text(self) -> str:
        return self.reason.toPlainText().strip()
