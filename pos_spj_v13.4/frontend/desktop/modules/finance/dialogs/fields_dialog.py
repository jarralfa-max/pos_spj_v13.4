"""Formulario declarativo de Finanzas (StandardDialog + FieldSpec).

Cada comando de Finanzas que sólo captura datos planos usa este diálogo en vez
de una clase propia: los campos se declaran (``FieldSpec``) y el diálogo
valida obligatorios e importes antes de cerrar. Si algo falta, el diálogo
queda abierto y dice qué (auditoría F25).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Callable

from PyQt5.QtWidgets import QCheckBox, QComboBox, QLineEdit, QPlainTextEdit, QSpinBox

from frontend.desktop.components.date_input import DateInput
from frontend.desktop.components.money_input import MoneyInput
from frontend.desktop.components.search_selector import SearchOption, SearchSelector
from frontend.desktop.modules.finance.dialogs._form_dialog import FinanceFormDialog

#: Tipos de campo admitidos.
KINDS = ("text", "multiline", "money", "decimal", "int", "date", "combo", "search", "check",
         "info")


@dataclass
class FieldSpec:
    key: str
    label: str
    kind: str = "text"
    required: bool = False
    options: list[tuple[str, str]] = field(default_factory=list)
    #: ``search``: proveedor de opciones ``texto → [(id, etiqueta)]``.
    provider: Callable[[str], list[tuple[str, str]]] | None = None
    default: object = None
    placeholder: str = ""
    minimum: int = 0
    maximum: int = 9999
    #: ``money``: admite cero (por omisión un importe debe ser mayor que cero).
    allow_zero: bool = False

    def __post_init__(self) -> None:
        if self.kind not in KINDS:
            raise ValueError(f"Tipo de campo desconocido: {self.kind}")


class FieldsDialog(FinanceFormDialog):
    def __init__(self, parent, title: str, fields: list[FieldSpec], *,
                 validator: Callable[[dict], str | None] | None = None) -> None:
        self.dialog_title = title
        self._specs = fields
        self._validator = validator
        self.widgets: dict[str, object] = {}
        super().__init__(parent)

    # ── construcción ─────────────────────────────────────────────────────
    def _build_form(self) -> None:
        for spec in self._specs:
            widget = self._widget_for(spec)
            self.widgets[spec.key] = widget
            label = f"{spec.label}{' *' if spec.required else ''}:"
            if spec.kind == "info":
                self.form.addRow(widget)
            elif spec.kind == "check":
                self.form.addRow(widget)
            else:
                self.form.addRow(label, widget)

    def _widget_for(self, spec: FieldSpec):
        if spec.kind == "info":
            from PyQt5.QtWidgets import QLabel
            label = QLabel(str(spec.default or spec.label), self)
            label.setWordWrap(True)
            label.setProperty("role", "muted")
            return label
        if spec.kind == "multiline":
            widget = QPlainTextEdit(self)
            widget.setMaximumHeight(90)
            widget.setPlaceholderText(spec.placeholder)
            if spec.default:
                widget.setPlainText(str(spec.default))
            return widget
        if spec.kind == "money":
            widget = MoneyInput(self)
            if spec.default not in (None, ""):
                widget.set_decimal_value(str(spec.default))
            return widget
        if spec.kind == "int":
            widget = QSpinBox(self)
            widget.setRange(spec.minimum, spec.maximum)
            widget.setValue(int(spec.default if spec.default is not None else spec.minimum))
            return widget
        if spec.kind == "date":
            widget = DateInput(self)
            widget.set_date_value(spec.default if isinstance(spec.default, date) else date.today())
            return widget
        if spec.kind == "combo":
            widget = QComboBox(self)
            if not spec.required:
                widget.addItem("—", None)
            for value, label in spec.options:
                widget.addItem(label, value)
            if spec.default is not None:
                index = widget.findData(spec.default)
                if index >= 0:
                    widget.setCurrentIndex(index)
            return widget
        if spec.kind == "search":
            provider = spec.provider or (lambda _text: [])
            return SearchSelector(
                self, keep_selection=True, placeholder=spec.placeholder or "Buscar…",
                provider=lambda text: [SearchOption(i, label) for i, label in provider(text)])
        if spec.kind == "check":
            widget = QCheckBox(spec.label, self)
            widget.setChecked(bool(spec.default))
            return widget
        widget = QLineEdit(self)
        widget.setPlaceholderText(spec.placeholder)
        if spec.default not in (None, ""):
            widget.setText(str(spec.default))
        return widget

    # ── lectura ──────────────────────────────────────────────────────────
    def _value(self, spec: FieldSpec):
        widget = self.widgets[spec.key]
        if spec.kind == "info":
            return None
        if spec.kind == "multiline":
            return widget.toPlainText().strip()
        if spec.kind == "money":
            return format(widget.decimal_value(), "f")
        if spec.kind == "int":
            return widget.value()
        if spec.kind == "date":
            return widget.date_value()
        if spec.kind == "combo":
            return widget.currentData()
        if spec.kind == "search":
            option = widget.selected_option()
            return option.id if option is not None else None
        if spec.kind == "check":
            return widget.isChecked()
        return widget.text().strip()

    def data(self) -> dict:
        return {spec.key: self._value(spec) for spec in self._specs if spec.kind != "info"}

    def _validation_error(self) -> str | None:
        values = self.data()
        for spec in self._specs:
            value = values.get(spec.key)
            if spec.kind == "money":
                amount = Decimal(value)
                if amount < 0 or (amount == 0 and (spec.required and not spec.allow_zero)):
                    return f"{spec.label}: el importe debe ser mayor que cero."
                continue
            if spec.kind == "decimal" and value:
                try:
                    Decimal(value)
                except InvalidOperation:
                    return f"{spec.label}: escriba un número decimal (punto como separador)."
            if spec.required and value in (None, "", []):
                return f"Falta: {spec.label}."
        return self._validator(values) if self._validator else None


def ask(parent, title: str, fields: list[FieldSpec], *,
        validator: Callable[[dict], str | None] | None = None) -> dict | None:
    """Abre el formulario; devuelve los valores o ``None`` si se canceló."""
    dialog = FieldsDialog(parent, title, fields, validator=validator)
    return dialog.data() if dialog.exec_() else None


def ask_reason(parent, title: str, label: str = "Motivo") -> str | None:
    values = ask(parent, title, [FieldSpec("reason", label, "multiline", required=True)])
    return values["reason"] if values else None


def ask_entity(parent, title: str, label: str,
               provider: Callable[[str], list[tuple[str, str]]]) -> tuple[str, str] | None:
    """Pide un cliente/proveedor por búsqueda; devuelve ``(id, etiqueta)``."""
    dialog = FieldsDialog(parent, title, [FieldSpec("entity", label, "search", required=True,
                                                    provider=provider)])
    if not dialog.exec_():
        return None
    option = dialog.widgets["entity"].selected_option()
    return (option.id, option.label) if option is not None else None
