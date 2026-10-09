"""Dialogs for the "Dispositivos" section — first real CRUD wired for
Configuración (SET-25 follow-up). Built entirely on `FormDialog`/
`ConfirmationDialog` (FASE DS-3), never a raw `QDialog`.
"""

from __future__ import annotations

from PyQt5.QtWidgets import QCheckBox, QDialogButtonBox, QVBoxLayout, QWidget

from frontend.desktop.components import (
    FormDialog,
    IntegerInput,
    SearchableComboBox,
    StandardLineEdit,
    StandardTextArea,
    apply_tooltip,
)

# Cajones de dinero y terminales de pago no aparecen: los administra Caja.
_DEVICE_TYPES = (
    ("THERMAL_PRINTER", "Impresora térmica"), ("LABEL_PRINTER", "Impresora de etiquetas"),
    ("DOCUMENT_PRINTER", "Impresora de documentos"), ("SCALE", "Báscula"),
    ("BARCODE_SCANNER", "Lector de código de barras"), ("QR_SCANNER", "Lector QR"),
    ("CUSTOMER_DISPLAY", "Pantalla del cliente"), ("TEMPERATURE_SENSOR", "Sensor de temperatura"),
    ("CARD_PRINTER", "Impresora de tarjetas"), ("MOBILE_DEVICE", "Dispositivo móvil"),
    ("OTHER", "Otro"),
)

# HTTP/WEBSOCKET deliberately not offered yet — see
# docs/refactor/SET-25_legacy_removal_report.md.
_CONNECTION_TYPES = (
    ("USB", "USB"), ("SERIAL", "Puerto serie (COM)"), ("NETWORK", "Red (host/puerto)"),
    ("BLUETOOTH", "Bluetooth"), ("SYSTEM", "Sistema"), ("VIRTUAL", "Virtual"),
)

_BAUD_RATES = (300, 1200, 2400, 4800, 9600, 19200, 38400, 57600, 115200)

# §23 — only meaningful when device_type is one of the 4 printer types
# (THERMAL_PRINTER/LABEL_PRINTER/DOCUMENT_PRINTER/CARD_PRINTER); the use
# case validates this via printer_profile_policy.assert_valid_printer_profile()
# when it applies, so an unrelated device_type never trips on these.
_PAPER_PROFILES = (
    ("PAPER_58MM", "58mm térmico"), ("PAPER_80MM", "80mm térmico"), ("A4", "A4"),
    ("LETTER", "Carta"), ("LABEL", "Etiqueta"), ("CARD", "Tarjeta"), ("PDF", "PDF"),
    ("VIRTUAL", "Virtual"),
)
_PRINTER_PROTOCOLS = (
    ("ESC_POS", "ESC/POS"), ("ZPL", "ZPL"), ("PDF", "PDF"), ("HTML", "HTML"), ("RAW", "Raw"),
)
# §22 — only meaningful when device_type is SCALE; the use case validates
# via scale_profile_policy.assert_valid_scale_profile() when it applies.
# `protocol` is one shared field on DeviceProfile regardless of device
# type, so the dialog offers both vocabularies in one combo — whichever
# one applies is enforced server-side, not by hiding options client-side.
_SCALE_PROTOCOLS = (
    ("TOLEDO_STANDARD", "Toledo estándar"), ("SICS", "SICS"), ("NCI", "NCI"),
    ("CONTINUOUS", "Continuo"), ("ON_DEMAND", "Bajo demanda"),
)
_PROTOCOLS = _PRINTER_PROTOCOLS + _SCALE_PROTOCOLS + (("VIRTUAL", "Virtual"),)
class DeviceProfileCreateDialog(FormDialog):
    """Registers a `DeviceProfile` (the reusable connection/capability
    template one or more `Device`s point at). Serial/network fields are
    always shown; the use case only consumes the ones the chosen
    `connection_type` actually needs. Same for paper_profile/protocol —
    always shown, only validated (§23: "no asumir que toda impresora es
    ESC/POS"; §22 for scales) when `device_type` is a printer/scale. The
    capability a scale (WEIGH), reader (SCAN_1D/SCAN_2D), or cash drawer
    (DRAWER_PULSE) profile needs is derived from `device_type` by the use
    case itself, not asked here — a payment terminal's capabilities are
    the one exception, a genuine choice via the checkboxes below."""

    def __init__(self, parent=None, *, windows_printers=()) -> None:
        super().__init__(parent, title="Nuevo perfil de dispositivo")
        self.name = StandardLineEdit(self)
        self.name.setAccessibleName("Nombre del perfil")
        apply_tooltip(self.name, "Ej. «Epson TM-T20III USB 80mm».")
        self.form.addRow("Nombre:", self.name)

        self.device_type = SearchableComboBox(self, placeholder="Selecciona un tipo…")
        self.device_type.set_options(_DEVICE_TYPES)
        self.device_type.setAccessibleName("Tipo de dispositivo")
        self.form.addRow("Tipo:", self.device_type)

        self.connection_type = SearchableComboBox(self, placeholder="Selecciona una conexión…")
        self.connection_type.set_options(_CONNECTION_TYPES)
        self.connection_type.setAccessibleName("Tipo de conexión")
        self.form.addRow("Conexión:", self.connection_type)

        self.manufacturer = StandardLineEdit(self)
        self.manufacturer.setAccessibleName("Fabricante")
        self.form.addRow("Fabricante:", self.manufacturer)

        self.model = StandardLineEdit(self)
        self.model.setAccessibleName("Modelo")
        self.form.addRow("Modelo:", self.model)

        self.serial_port = StandardLineEdit(self)
        self.serial_port.setAccessibleName("Puerto serie")
        apply_tooltip(self.serial_port, "Solo si la conexión es Puerto serie. Ej. «COM3».")
        self.form.addRow("Puerto (serie):", self.serial_port)

        self.baud_rate = SearchableComboBox(self, placeholder="Baud rate…")
        self.baud_rate.set_options([(rate, str(rate)) for rate in _BAUD_RATES])
        self.baud_rate.setAccessibleName("Baud rate")
        self.form.addRow("Baud rate (serie):", self.baud_rate)

        self.host = StandardLineEdit(self)
        self.host.setAccessibleName("Host")
        apply_tooltip(self.host, "Solo si la conexión es Red. Ej. «192.168.1.50».")
        self.form.addRow("Host (red):", self.host)

        self.port = IntegerInput(self, minimum=1, maximum=65535)
        self.port.setValue(9100)
        self.port.setAccessibleName("Puerto de red")
        self.form.addRow("Puerto (red):", self.port)

        self.paper_profile = SearchableComboBox(self, placeholder="Selecciona un perfil de papel…")
        self.paper_profile.set_options(_PAPER_PROFILES)
        self.paper_profile.setAccessibleName("Perfil de papel")
        self.form.addRow("Papel (solo impresoras):", self.paper_profile)

        self.protocol = SearchableComboBox(self, placeholder="Selecciona un protocolo…")
        self.protocol.set_options(_PROTOCOLS)
        self.protocol.setAccessibleName("Protocolo")
        self.form.addRow("Protocolo (impresoras/básculas):", self.protocol)

        # USB: la cola de Windows a la que se envía. Se ELIGE de las instaladas;
        # vacío = la predeterminada de Windows (que puede no ser la térmica).
        self.windows_printer = SearchableComboBox(self, placeholder="Predeterminada de Windows")
        self.windows_printer.set_options([(n, n) for n in windows_printers])
        self.windows_printer.setAccessibleName("Impresora de Windows")
        apply_tooltip(self.windows_printer,
                      "Sólo para conexión USB: la impresora instalada en Windows que recibe los tickets.")
        self.form.addRow("Impresora de Windows (USB):", self.windows_printer)


        self.add_button_box(ok_text="Crear perfil")

    def values(self) -> dict:
        return {
            "name": self.name.text().strip(), "device_type": self.device_type.current_id(),
            "connection_type": self.connection_type.current_id(),
            "manufacturer": self.manufacturer.text().strip(), "model": self.model.text().strip(),
            "serial_port": self.serial_port.text().strip(), "baud_rate": self.baud_rate.current_id(),
            "host": self.host.text().strip(), "port": self.port.value(),
            "paper_profile": self.paper_profile.current_id() or "",
            "protocol": self.protocol.current_id() or "",
            "driver_name": self.windows_printer.current_id() or "",
        }


class DeviceCreateDialog(FormDialog):
    def __init__(self, parent=None, *, branch_options=(), profile_options=()) -> None:
        super().__init__(parent, title="Nuevo dispositivo")
        self.branch = SearchableComboBox(self, placeholder="Selecciona una sucursal…")
        self.branch.set_options([(o.entity_id, o.name) for o in branch_options])
        self.branch.setAccessibleName("Sucursal")
        self.form.addRow("Sucursal:", self.branch)

        self.profile = SearchableComboBox(self, placeholder="Selecciona un perfil…")
        self.profile.set_options([
            (o.entity_id, f"{o.name} ({o.device_type})") for o in profile_options
        ])
        self.profile.setAccessibleName("Perfil de dispositivo")
        self.form.addRow("Perfil:", self.profile)

        self.code = StandardLineEdit(self)
        self.code.setAccessibleName("Código")
        apply_tooltip(self.code, "Identificador corto único. Ej. «PRN-01».")
        self.form.addRow("Código:", self.code)

        self.name = StandardLineEdit(self)
        self.name.setAccessibleName("Nombre")
        self.form.addRow("Nombre:", self.name)

        self.hardware_identifier = StandardLineEdit(self)
        self.hardware_identifier.setAccessibleName("Identificador de hardware")
        apply_tooltip(self.hardware_identifier, "Opcional. Número de serie, MAC, etc.")
        self.form.addRow("Identificador (opcional):", self.hardware_identifier)

        self.notes = StandardTextArea(self)
        self.notes.setAccessibleName("Notas")
        self.form.addRow("Notas:", self.notes)

        self.add_button_box(ok_text="Registrar")

    def values(self) -> dict:
        return {
            "branch_id": self.branch.current_id(), "profile_id": self.profile.current_id(),
            "code": self.code.text().strip(), "name": self.name.text().strip(),
            "hardware_identifier": self.hardware_identifier.text().strip(),
            "notes": self.notes.toPlainText().strip(),
        }


class DeviceEditDialog(FormDialog):
    def __init__(self, parent=None, *, name: str = "", notes: str = "") -> None:
        super().__init__(parent, title="Editar dispositivo")
        self.name = StandardLineEdit(self)
        self.name.setText(name)
        self.name.setAccessibleName("Nombre")
        self.form.addRow("Nombre:", self.name)

        self.notes = StandardTextArea(self)
        self.notes.setPlainText(notes)
        self.notes.setAccessibleName("Notas")
        self.form.addRow("Notas:", self.notes)

        self.add_button_box(ok_text="Guardar")

    def values(self) -> dict:
        return {"name": self.name.text().strip(), "notes": self.notes.toPlainText().strip()}


class BlockDeviceDialog(FormDialog):
    """Blocking a `Device` always requires a reason — the domain
    (`Device.block`) rejects a blank one, so this dialog can't be
    submitted without one either. Mirrors
    `dialogs/feature_flag_dialogs.py::RejectChangeRequestDialog`."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent, title="Bloquear dispositivo")
        self.reason = StandardTextArea(self)
        self.reason.setAccessibleName("Motivo de bloqueo")
        apply_tooltip(self.reason, "Explica por qué se bloquea este dispositivo.")
        self.form.addRow("Motivo:", self.reason)
        box = self.add_button_box(ok_text="Bloquear")
        self._ok_button = box.button(QDialogButtonBox.Ok)
        self._ok_button.setEnabled(False)
        self.reason.textChanged.connect(self._on_text_changed)

    def _on_text_changed(self) -> None:
        self._ok_button.setEnabled(bool(self.reason_text()))

    def reason_text(self) -> str:
        return self.reason.toPlainText().strip()


class WindowsPrinterDialog(FormDialog):
    """Elige la impresora de Windows (cola USB) del dispositivo seleccionado."""

    def __init__(self, parent=None, *, device_name: str = "", current: str = "",
                 windows_printers=()) -> None:
        super().__init__(parent, title=f"Impresora de Windows de {device_name}")
        self.printer = SearchableComboBox(self, placeholder="Predeterminada de Windows")
        self.printer.set_options([(n, n) for n in windows_printers])
        if current:
            self.printer.set_current_id(current)
        self.printer.setAccessibleName("Impresora de Windows")
        self.form.addRow("Impresora:", self.printer)
        self.add_button_box(ok_text="Guardar")

    def printer_name(self) -> str:
        return self.printer.current_id() or ""
