"""Diálogo genérico de una acción de Fidelidad (LOY-29).

Arma el formulario a partir de los `FieldSpec` de la acción, valida que lo
obligatorio esté capturado y entrega los valores ya convertidos (Decimal, int,
fecha ISO, valor de Enum). No decide nada del negocio: si la acción no procede,
lo dice el caso de uso.
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation

from PyQt5.QtWidgets import QHBoxLayout, QLabel, QWidget

from frontend.desktop.components import (
    CustomerSearchBox,
    FormField,
    IntegerInput,
    MoneyInput,
    SearchableComboBox,
    StandardForm,
)
from frontend.desktop.components.date_input import DateInput
from frontend.desktop.components.decimal_input import DecimalInput
from frontend.desktop.components.dialogs import StandardDialog
from frontend.desktop.components.search_selector import SearchOption
from frontend.desktop.components.selection_controls import StandardCheckBox
from frontend.desktop.components.text_inputs import StandardLineEdit, StandardTextArea
from frontend.desktop.modules.fidelidad.records.labels import options_for
from frontend.desktop.modules.fidelidad.records.specs import ActionSpec, FieldKind, FieldSpec
from frontend.desktop.themes.tokens import DialogMetrics, Spacing


class _OptionalDate(QWidget):
    """Fecha que puede quedar sin definir (vigencia abierta)."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(Spacing.SM)
        self.enabled = StandardCheckBox("Definir", self)
        self.date = DateInput(self)
        self.date.setEnabled(False)
        self.enabled.toggled.connect(self.date.setEnabled)
        layout.addWidget(self.enabled)
        layout.addWidget(self.date, stretch=1)

    def iso(self) -> str | None:
        return self.date.date_value().isoformat() if self.enabled.isChecked() else None


class _CustomerField(QWidget):
    def __init__(self, provider, parent=None) -> None:
        super().__init__(parent)
        from PyQt5.QtWidgets import QVBoxLayout

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.box = CustomerSearchBox(self, provider=provider)
        self.box.selected.connect(self._on_selected)
        self.chosen = QLabel("", self)
        self.chosen.setProperty("role", "muted")
        layout.addWidget(self.box)
        layout.addWidget(self.chosen)
        self.customer_id: str | None = None

    def _on_selected(self, option: SearchOption) -> None:
        self.customer_id = option.id
        self.box.set_selected_label(option.label)
        self.chosen.setText(f"Cliente: {option.label}")


class ActionDialog(StandardDialog):
    def __init__(self, action: ActionSpec, presenter, parent=None) -> None:
        super().__init__(parent, title=action.label, width=DialogMetrics.WIDTH_MD)
        self.setObjectName("fidelidadActionDialog")
        self._action = action
        self._presenter = presenter
        self._widgets: dict[str, QWidget] = {}
        self.form = StandardForm(self)
        for spec in action.fields:
            widget = self._build(spec)
            self._widgets[spec.key] = widget
            self.form.add_field(spec.key, FormField(
                spec.label, widget, required=spec.required, helper=spec.helper or None))
        self.content_layout().addWidget(self.form)
        if action.confirm:
            aviso = QLabel(action.confirm, self)
            aviso.setWordWrap(True)
            self.content_layout().addWidget(aviso)
        self.add_button_box(ok_text=action.label)

    # ── construcción ───────────────────────────────────────────────────────
    def _build(self, spec: FieldSpec) -> QWidget:
        kind = spec.kind
        if kind is FieldKind.MULTILINE:
            return StandardTextArea(self)
        if kind is FieldKind.INTEGER:
            widget = IntegerInput(self)
            if spec.default is not None:
                widget.setValue(int(spec.default))
            return widget
        if kind is FieldKind.MONEY:
            widget = MoneyInput(self)
            if spec.default is not None:
                widget.set_decimal_value(Decimal(str(spec.default)))
            return widget
        if kind is FieldKind.DECIMAL:
            widget = DecimalInput(self)
            if spec.default is not None:
                widget.set_decimal(Decimal(str(spec.default)))
            return widget
        if kind is FieldKind.DATE:
            return _OptionalDate(self) if not spec.required else DateInput(self)
        if kind is FieldKind.BOOL:
            widget = StandardCheckBox(spec.label, self)
            widget.setChecked(bool(spec.default) if spec.default is not None else True)
            return widget
        if kind is FieldKind.CHOICE:
            widget = SearchableComboBox(self)
            widget.set_options(options_for(spec.enum, spec.only))
            if spec.default is not None:
                widget.set_current_id(spec.default)
            return widget
        if kind is FieldKind.CUSTOMER:
            return _CustomerField(self._presenter.customer_options, self)
        if kind is FieldKind.RECORD:
            widget = SearchableComboBox(self)
            widget.set_options(self._presenter.record_options(
                spec.record, spec.record_label, dict(spec.record_filters)))
            return widget
        widget = StandardLineEdit(self)
        if spec.default is not None:
            widget.setText(str(spec.default))
        return widget

    # ── lectura ────────────────────────────────────────────────────────────
    def values(self) -> dict | None:
        """Valores convertidos, o None si falta algo (y marca el campo)."""
        errores: dict[str, str] = {}
        valores: dict = {}
        for spec in self._action.fields:
            try:
                valor = self._read(spec)
            except (InvalidOperation, ValueError):
                errores[spec.key] = "Valor no válido."
                continue
            if spec.required and valor in (None, ""):
                errores[spec.key] = "Este dato es obligatorio."
                continue
            if valor not in (None, ""):
                valores[spec.key] = valor
        self.form.set_errors(errores)
        return None if errores else valores

    def _read(self, spec: FieldSpec):
        widget = self._widgets[spec.key]
        kind = spec.kind
        if kind in (FieldKind.TEXT,):
            return widget.text().strip()
        if kind is FieldKind.MULTILINE:
            return widget.value().strip()
        if kind is FieldKind.INTEGER:
            return int(widget.value())
        if kind is FieldKind.MONEY:
            valor = widget.decimal_value()
            return valor if (valor > 0 or not spec.required) else None
        if kind is FieldKind.DECIMAL:
            texto = widget.text().strip()
            return Decimal(texto) if texto else None
        if kind is FieldKind.DATE:
            return widget.iso() if isinstance(widget, _OptionalDate) else (
                widget.date_value().isoformat())
        if kind is FieldKind.BOOL:
            return widget.isChecked()
        if kind is FieldKind.CHOICE:
            valor = widget.current_id()
            return spec.enum(valor) if (valor and spec.enum is not None) else None
        if kind is FieldKind.CUSTOMER:
            return widget.customer_id
        if kind is FieldKind.RECORD:
            return widget.current_id() or None
        return None

    def accept(self) -> None:  # noqa: D401 — Qt override
        if self.values() is None:
            return
        super().accept()


__all__ = ["ActionDialog"]
