"""Diálogos de Logística → Contenedores. Sólo capturan y validan forma; la regla
la aplica el servicio. Validan ANTES de cerrar: un error no pierde lo capturado."""

from __future__ import annotations

from PyQt5.QtCore import Qt
from PyQt5.QtGui import QPixmap
from PyQt5.QtWidgets import QLabel

from frontend.desktop.components import (
    ColumnSpec,
    DecimalInput,
    FormDialog,
    IntegerInput,
    StandardLineEdit,
    StandardTable,
)
from frontend.desktop.components.searchable_combo import SearchableComboBox
from frontend.desktop.modules.logistics.logistics_presenter import OPERATIONAL_STATUS_OPTIONS


class _ValidatedDialog(FormDialog):
    def __init__(self, parent=None, *, title: str, ok_text: str) -> None:
        super().__init__(parent, title=title)
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


class ContainerEditDialog(_ValidatedDialog):
    """Tara, capacidad, serie y ubicación. Código, tipo y dueño no se editan:
    son la identidad que lleva impresa el QR."""

    def __init__(self, parent=None, *, container: dict) -> None:
        super().__init__(parent, title=f"Editar {container['code']}", ok_text="Guardar")
        self.tare = DecimalInput(self, precision=3, minimum="0", suffix="kg")
        self.tare.set_decimal(container.get("tare_weight") or "0")
        self.capacity = DecimalInput(self, precision=3, minimum="0", suffix="kg", nullable=True)
        self.capacity.set_decimal(container.get("capacity_weight"))
        self.serial = StandardLineEdit(self)
        self.serial.setText(container.get("serial_number") or "")
        self.location = StandardLineEdit(self)
        self.location.setPlaceholderText("Ubicación o custodio (ej. Andén 2)")
        self.location.setText(container.get("location_id") or "")
        self.form.addRow("Tara:", self.tare)
        self.form.addRow("Capacidad:", self.capacity)
        self.form.addRow("Número de serie:", self.serial)
        self.form.addRow("Ubicación:", self.location)
        self._finish()

    def values(self) -> dict:
        capacidad = self.capacity.decimal_value()
        return {"tare_weight": self.tare.decimal_value(),
                "capacity_weight": "" if capacidad is None else capacidad,
                "serial_number": self.serial.text(), "location_id": self.location.text().strip()}


class ContainerStatusDialog(_ValidatedDialog):
    def __init__(self, parent=None, *, container: dict) -> None:
        super().__init__(parent, title=f"Estado de {container['code']}", ok_text="Cambiar estado")
        aviso = QLabel(f"Estado actual: {container.get('status_label', '')}", self)
        self.form.addRow(aviso)
        self.status = SearchableComboBox(placeholder="Nuevo estado")
        self.status.set_options(list(OPERATIONAL_STATUS_OPTIONS))
        self.reason = StandardLineEdit(self, placeholder="Motivo (obligatorio)")
        self.form.addRow("Nuevo estado:", self.status)
        self.form.addRow("Motivo:", self.reason)
        self._finish()

    def problem(self) -> str | None:
        if not self.status.current_id():
            return "Elige el nuevo estado."
        if not self.reason.text().strip():
            return "Captura el motivo."
        return None


class ContainerLabelDialog(_ValidatedDialog):
    """Etiquetas QR de los contenedores elegidos: formato (etiqueta, hoja o
    térmica), copias y vista previa real. Si alguna ya se imprimió es una
    REIMPRESIÓN y el motivo es obligatorio.

    ``preview(fmt) -> bytes | None`` da el PNG de la primera etiqueta."""

    def __init__(self, parent=None, *, codes: list[str], formats, preview,
                 reprinted: list[str]) -> None:
        titulo = (f"Etiqueta de {codes[0]}" if len(codes) == 1
                  else f"Etiquetas de {len(codes)} contenedores")
        super().__init__(parent, title=titulo, ok_text="Generar")
        self._preview = preview
        self._reprinted = list(reprinted)
        lista = ", ".join(codes[:8]) + (f" y {len(codes) - 8} más" if len(codes) > 8 else "")
        resumen = QLabel(lista, self)
        resumen.setWordWrap(True)
        self.form.addRow("Contenedores:", resumen)
        self.format = SearchableComboBox(placeholder="Formato")
        self.format.set_options(list(formats))
        self.copies = IntegerInput(self, minimum=1, maximum=20)
        self.form.addRow("Formato:", self.format)
        self.form.addRow("Copias de cada una:", self.copies)
        self.image = QLabel(self)
        self.image.setAlignment(Qt.AlignCenter)
        self.image.setMinimumHeight(200)
        self.form.addRow(self.image)
        self.reason = StandardLineEdit(self, placeholder="Motivo (ej. etiqueta dañada)")
        if self._reprinted:
            aviso = QLabel("Ya se imprimió la etiqueta de " + ", ".join(self._reprinted[:5])
                           + ("…" if len(self._reprinted) > 5 else "")
                           + ": esto es una reimpresión (el QR es el mismo).", self)
            aviso.setWordWrap(True)
            self.form.addRow(aviso)
            self.form.addRow("Motivo:", self.reason)
        else:
            self.reason.hide()
        self.format.selection_changed.connect(lambda *_: self._refresh())
        if formats:
            self.format.set_current_id(formats[0][0])
        self._refresh()
        self._finish()

    def _refresh(self) -> None:
        fmt = self.format.current_id()
        datos = self._preview(fmt) if fmt else None
        if not datos:
            self.image.setText("Vista previa no disponible")
            return
        imagen = QPixmap()
        imagen.loadFromData(datos, "PNG")
        self.image.setPixmap(imagen.scaledToWidth(min(560, imagen.width()),
                                                  Qt.SmoothTransformation))

    def selected_format(self) -> str:
        return str(self.format.current_id() or "")

    def problem(self) -> str | None:
        if not self.format.current_id():
            return "Elige el formato."
        if self._reprinted and not self.reason.text().strip():
            return "Captura el motivo de la reimpresión."
        return None

    def values(self) -> dict:
        return {"fmt": self.selected_format(), "copies": self.copies.value(),
                "reason": self.reason.text().strip()}


class ContainerHistoryDialog(FormDialog):
    def __init__(self, parent=None, *, container: dict, history: list[dict]) -> None:
        super().__init__(parent, title=f"Historial de {container['code']}", width=760)
        tabla = StandardTable(columns=[ColumnSpec("Fecha"), ColumnSpec("Tipo"),
                                       ColumnSpec("Acción"), ColumnSpec("Quién"),
                                       ColumnSpec("Motivo")])
        tabla.load_rows([[str(h["at"] or "")[:16].replace("T", " "), h["source"], h["action"],
                          h.get("actor_name") or "", h["reason"]] for h in history],
                        row_ids=[str(i) for i in range(len(history))])
        self.form.addRow(tabla)
        if not history:
            self.form.addRow(QLabel("Sin movimientos registrados.", self))
        self.add_button_box(ok_text="Cerrar")
