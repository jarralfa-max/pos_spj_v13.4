"""Inventory action dialogs (P0-B/P0-C/P0-D — Cuarentena, Ajustes, Conteos,
Almacenes, Ubicaciones).

Presentation-only: capture values for the corresponding use cases (open,
dispose, create, reverse, capturar, confirmar, activar, bloquear). No
business logic, no backend calls — the page reads the captured values and
hands them to the presenter after the dialog is accepted. Product selection
goes through the canonical search provider (§P0-D) — never a hand-typed UUID.
"""

from __future__ import annotations

from PyQt5.QtWidgets import QCheckBox, QComboBox, QSpinBox

from frontend.desktop.components.decimal_input import DecimalInput
from frontend.desktop.components.dialogs import FormDialog
from frontend.desktop.components.entity_search_input import EntitySearchInput
from frontend.desktop.components.text_inputs import StandardLineEdit, StandardTextArea
from frontend.desktop.modules.inventory.view_models import (
    ADJUSTMENT_REASON_ES,
    COUNT_TYPE_ES,
    QUARANTINE_REASON_ES,
    WAREHOUSE_TYPE_ES,
)


class DisposeQuarantineDialog(FormDialog):
    """Motivo de disposición (baja definitiva) de una cuarentena — auditado."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent, title="Disponer cuarentena")
        self.reason_input = StandardTextArea(self, placeholder="Motivo de la disposición…")
        self.reason_input.setMaximumHeight(90)
        self.form.addRow("Motivo:", self.reason_input)
        self.add_button_box(ok_text="Disponer")

    def reason(self) -> str:
        return self.reason_input.value()


class OpenQuarantineDialog(FormDialog):
    """Poner stock en cuarentena: producto (búsqueda canónica), motivo,
    ubicación real (opcional — lista acotada del almacén, §P0-04 corolario) y
    cantidad."""

    def __init__(self, parent=None, *, product_provider, location_options=None) -> None:
        super().__init__(parent, title="Nueva cuarentena")
        self.product = EntitySearchInput(
            self, provider=product_provider,
            placeholder="Buscar producto por nombre, código o código de barras…")
        self.reason_combo = QComboBox(self)
        for code, label in QUARANTINE_REASON_ES.items():
            self.reason_combo.addItem(label, code)
        self.location_combo = QComboBox(self)
        self.location_combo.addItem("Automática (todo el almacén)", "")
        for option in (location_options or []):
            self.location_combo.addItem(option.label, option.id)
        self.quantity = DecimalInput(self, precision=3, minimum="0.001")
        self.note_input = StandardTextArea(self, placeholder="Nota (opcional)…")
        self.note_input.setMaximumHeight(70)
        self.form.addRow("Producto:", self.product)
        self.form.addRow("Motivo:", self.reason_combo)
        self.form.addRow("Ubicación:", self.location_combo)
        self.form.addRow("Cantidad:", self.quantity)
        self.form.addRow("Nota:", self.note_input)
        self.add_button_box(ok_text="Poner en cuarentena")

    def product_id(self) -> str | None:
        return self.product.selected_id()

    def reason_code(self) -> str:
        return str(self.reason_combo.currentData() or "")

    def location_id(self) -> str | None:
        return str(self.location_combo.currentData() or "") or None

    def quantity_value(self):
        return self.quantity.decimal_value()

    def note(self) -> str:
        return self.note_input.value()


class CreateAdjustmentDialog(FormDialog):
    """Nuevo ajuste de una sola línea: producto (búsqueda canónica), motivo,
    dirección (entrada/salida) y magnitud — el signo se arma aquí, el usuario
    nunca teclea un menos."""

    def __init__(self, parent=None, *, product_provider) -> None:
        super().__init__(parent, title="Nuevo ajuste")
        self.product = EntitySearchInput(
            self, provider=product_provider,
            placeholder="Buscar producto por nombre, código o código de barras…")
        self.reason_combo = QComboBox(self)
        for code, label in ADJUSTMENT_REASON_ES.items():
            self.reason_combo.addItem(label, code)
        self.direction_combo = QComboBox(self)
        self.direction_combo.addItem("Entrada (+)", "in")
        self.direction_combo.addItem("Salida (-)", "out")
        self.quantity = DecimalInput(self, precision=3, minimum="0.001")
        self.note_input = StandardTextArea(self, placeholder="Nota (opcional)…")
        self.note_input.setMaximumHeight(70)
        self.form.addRow("Producto:", self.product)
        self.form.addRow("Motivo:", self.reason_combo)
        self.form.addRow("Dirección:", self.direction_combo)
        self.form.addRow("Cantidad:", self.quantity)
        self.form.addRow("Nota:", self.note_input)
        self.add_button_box(ok_text="Crear ajuste")

    def product_id(self) -> str | None:
        return self.product.selected_id()

    def reason_code(self) -> str:
        return str(self.reason_combo.currentData() or "")

    def quantity_delta(self):
        magnitude = self.quantity.decimal_value()
        if magnitude is None:
            return None
        return -magnitude if self.direction_combo.currentData() == "out" else magnitude

    def note(self) -> str:
        return self.note_input.value()


class ReverseAdjustmentDialog(FormDialog):
    """Motivo de reverso de un ajuste posteado — auditado, irreversible."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent, title="Reversar ajuste")
        self.reason_input = StandardTextArea(self, placeholder="Motivo del reverso…")
        self.reason_input.setMaximumHeight(90)
        self.form.addRow("Motivo:", self.reason_input)
        self.add_button_box(ok_text="Reversar")

    def reason(self) -> str:
        return self.reason_input.value()


class CreateCountDialog(FormDialog):
    """Nuevo conteo de una sola línea (§27): producto (búsqueda canónica),
    tipo de conteo y modalidad (a ciegas por defecto — no se muestra la
    cantidad esperada durante la captura)."""

    def __init__(self, parent=None, *, product_provider) -> None:
        super().__init__(parent, title="Nuevo conteo")
        self.product = EntitySearchInput(
            self, provider=product_provider,
            placeholder="Buscar producto por nombre, código o código de barras…")
        self.type_combo = QComboBox(self)
        for code, label in COUNT_TYPE_ES.items():
            self.type_combo.addItem(label, code)
        self.blind_check = QCheckBox("Conteo a ciegas (no muestra la cantidad esperada)", self)
        self.blind_check.setChecked(True)
        self.form.addRow("Producto:", self.product)
        self.form.addRow("Tipo:", self.type_combo)
        self.form.addRow("", self.blind_check)
        self.add_button_box(ok_text="Iniciar conteo")

    def product_id(self) -> str | None:
        return self.product.selected_id()

    def count_type_code(self) -> str:
        return str(self.type_combo.currentData() or "")

    def blind(self) -> bool:
        return self.blind_check.isChecked()


class RecordCountDialog(FormDialog):
    """Captura la cantidad contada de la línea (§27) — sin exponer la
    cantidad esperada cuando el conteo es a ciegas."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent, title="Capturar conteo")
        self.quantity = DecimalInput(self, precision=3, minimum="0")
        self.form.addRow("Cantidad contada:", self.quantity)
        self.add_button_box(ok_text="Capturar")

    def counted_quantity(self):
        return self.quantity.decimal_value()


class CreateWarehouseDialog(FormDialog):
    """Alta de almacén (§12): código, nombre y tipo. Sin ubicaciones técnicas
    aquí — eso lo hace el aprovisionamiento por defecto (P0-E) cuando aplica;
    esta alta manual es para almacenes adicionales con nombre propio."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent, title="Nuevo almacén")
        self.code_input = StandardLineEdit(self, placeholder="Código (p.ej. WH-002)")
        self.name_input = StandardLineEdit(self, placeholder="Nombre")
        self.type_combo = QComboBox(self)
        for code, label in WAREHOUSE_TYPE_ES.items():
            self.type_combo.addItem(label, code)
        self.form.addRow("Código:", self.code_input)
        self.form.addRow("Nombre:", self.name_input)
        self.form.addRow("Tipo:", self.type_combo)
        self.add_button_box(ok_text="Crear almacén")

    def code(self) -> str:
        return self.code_input.value()

    def name(self) -> str:
        return self.name_input.value()

    def warehouse_type(self) -> str:
        return str(self.type_combo.currentData() or "")


class CreateLocationDialog(FormDialog):
    """Alta de ubicación (§12): código, nombre y nivel. ``parent_label`` — si
    se abrió desde el menú contextual de una ubicación existente — deja claro
    que se está creando una sub-ubicación, no una raíz nueva."""

    def __init__(self, parent=None, *, parent_label: str | None = None) -> None:
        title = (f"Nueva sub-ubicación de «{parent_label}»" if parent_label
                 else "Nueva ubicación")
        super().__init__(parent, title=title)
        self.code_input = StandardLineEdit(self, placeholder="Código (p.ej. A1)")
        self.name_input = StandardLineEdit(self, placeholder="Nombre")
        self.level_spin = QSpinBox(self)
        self.level_spin.setRange(0, 10)
        self.form.addRow("Código:", self.code_input)
        self.form.addRow("Nombre:", self.name_input)
        self.form.addRow("Nivel:", self.level_spin)
        self.add_button_box(ok_text="Crear ubicación")

    def code(self) -> str:
        return self.code_input.value()

    def name(self) -> str:
        return self.name_input.value()

    def level(self) -> int:
        return self.level_spin.value()


class BlockReasonDialog(FormDialog):
    """Motivo de bloqueo — reutilizado por Almacenes y Ubicaciones: ambos
    bloquean por el mismo tipo de razón operativa (mantenimiento, cierre,
    incidente) y no ameritan dos clases casi idénticas."""

    def __init__(self, parent=None, *, title: str = "Bloquear") -> None:
        super().__init__(parent, title=title)
        self.reason_input = StandardTextArea(self, placeholder="Motivo del bloqueo…")
        self.reason_input.setMaximumHeight(90)
        self.form.addRow("Motivo:", self.reason_input)
        self.add_button_box(ok_text="Bloquear")

    def reason(self) -> str:
        return self.reason_input.value()
