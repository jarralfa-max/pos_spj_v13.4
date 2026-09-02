"""Dialog for the "Asignar dispositivo" action on the Estaciones
(General) section — SET-7's Assignments pillar had zero UI before this
round (Devices/Profiles were closed by the Dispositivos round).
"""

from __future__ import annotations

from frontend.desktop.components import FormDialog, SearchableComboBox

_ASSIGNMENT_ROLES = (
    ("PRIMARY_RECEIPT_PRINTER", "Impresora de recibo (principal)"),
    ("SECONDARY_RECEIPT_PRINTER", "Impresora de recibo (secundaria)"),
    ("LABEL_PRINTER", "Impresora de etiquetas"),
    ("KITCHEN_PRINTER", "Impresora de cocina"),
    ("PRODUCTION_PRINTER", "Impresora de producción"),
    ("TRANSFER_PRINTER", "Impresora de transferencias"),
    ("SCALE", "Báscula"),
    ("SCANNER", "Lector de código de barras/QR"),
    ("CASH_DRAWER", "Cajón de dinero"),
    ("PAYMENT_TERMINAL", "Terminal de pago"),
    ("CUSTOMER_DISPLAY", "Pantalla del cliente"),
)


class AssignDeviceDialog(FormDialog):
    def __init__(self, parent=None, *, device_options=()) -> None:
        super().__init__(parent, title="Asignar dispositivo")
        self.role = SearchableComboBox(self, placeholder="Selecciona un rol…")
        self.role.set_options(_ASSIGNMENT_ROLES)
        self.role.setAccessibleName("Rol")
        self.form.addRow("Rol:", self.role)

        self.device = SearchableComboBox(self, placeholder="Selecciona un dispositivo…")
        self.device.set_options([
            (o.entity_id, f"{o.name} ({o.device_type})" if o.device_type else o.name)
            for o in device_options
        ])
        self.device.setAccessibleName("Dispositivo")
        self.form.addRow("Dispositivo:", self.device)

        self.add_button_box(ok_text="Asignar")

    def values(self) -> dict:
        return {"role": self.role.current_id(), "device_id": self.device.current_id()}
