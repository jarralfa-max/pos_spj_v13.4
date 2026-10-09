"""Formulario declarativo de Clientes y CRM (CRM-43).

Cada acción con captura (nuevo prospecto, mover etapa, escalar un caso,
aprobar crédito…) describe sus campos con ``FieldSpec`` y abre un
``CrmFormDialog``: el diálogo canónico (``StandardDialog``) con un
``StandardForm`` de campos canónicos (``StandardLineEdit``, ``MoneyInput``,
``PhoneInput``, ``DateInput``, ``CustomerSearchBox``…), validación de
obligatorios en línea y un ``on_submit`` que recibe los valores ya tipados.

Si ``on_submit`` devuelve un resultado con ``success`` falso, el diálogo NO
se cierra: muestra el mensaje y conserva lo capturado (el usuario corrige y
reintenta; nunca pierde el formulario por un error de negocio).

Tipos de campo: text, textarea, choice, money, integer, percent, date,
datetime, phone, email, rfc, check, customer, user.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date, datetime

from PyQt5.QtWidgets import QLabel, QWidget

from frontend.desktop.components import (
    CustomerSearchBox,
    DateInput,
    DateTimeInput,
    EmailInput,
    FormField,
    IntegerInput,
    MoneyInput,
    PhoneInput,
    SearchableComboBox,
    SearchOption,
    StandardCheckBox,
    StandardDialog,
    StandardForm,
    StandardLineEdit,
    StandardTextArea,
    TaxIdentifierInput,
)
from frontend.desktop.modules.customers_crm.formatting import to_utc_iso
from frontend.desktop.themes.tokens import DialogMetrics


@dataclass(frozen=True)
class FieldSpec:
    key: str
    label: str
    kind: str = "text"
    required: bool = False
    options: tuple[tuple[str, str], ...] = ()
    default: object = None
    helper: str | None = None
    placeholder: str = ""
    minimum: int = 0
    maximum: int = 999999999
    #: Para ``customer``: etiqueta visible de ``default`` (el id).
    default_label: str = ""
    extra: dict = field(default_factory=dict)


class _CustomerField(QWidget):
    """``CustomerSearchBox`` que recuerda el cliente elegido."""

    def __init__(self, provider, parent=None) -> None:
        from PyQt5.QtWidgets import QVBoxLayout
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self._box = CustomerSearchBox(self, provider=provider, collapse_when_empty=True)
        self._box.selected.connect(self._on_selected)
        layout.addWidget(self._box)
        self._value: str | None = None

    def _on_selected(self, option) -> None:
        if isinstance(option, SearchOption):
            self._value = option.id
            self._box.set_selected_label(option.label)

    def set_value(self, customer_id: str | None, label: str = "") -> None:
        self._value = customer_id
        if customer_id:
            self._box.set_selected_label(label or customer_id)

    def value(self) -> str | None:
        return self._value


def build_input(spec: FieldSpec, parent, *, customer_provider=None, user_options=()):
    kind = spec.kind
    if kind == "textarea":
        widget = StandardTextArea(parent, placeholder=spec.placeholder)
        if spec.default:
            widget.setPlainText(str(spec.default))
        return widget
    if kind == "choice":
        widget = SearchableComboBox(parent, placeholder="Selecciona…")
        widget.set_options(list(spec.options))
        if spec.default is not None:
            widget.set_current_id(spec.default)
        return widget
    if kind == "user":
        widget = SearchableComboBox(parent, placeholder="Selecciona un usuario…")
        widget.set_options(list(user_options))
        if spec.default is not None:
            widget.set_current_id(spec.default)
        return widget
    if kind == "money":
        widget = MoneyInput(parent)
        if spec.default is not None:
            widget.set_decimal_value(spec.default)
        return widget
    if kind in ("integer", "percent"):
        maximum = 100 if kind == "percent" else spec.maximum
        widget = IntegerInput(parent, minimum=spec.minimum, maximum=maximum)
        if spec.default is not None:
            widget.setValue(int(spec.default))
        return widget
    if kind == "date":
        widget = DateInput(parent)
        if isinstance(spec.default, date):
            widget.set_date_value(spec.default)
        return widget
    if kind == "datetime":
        widget = DateTimeInput(parent)
        if isinstance(spec.default, datetime):
            widget.set_datetime_value(spec.default)
        return widget
    if kind == "phone":
        widget = PhoneInput(parent, required=spec.required)
        widget.set_value(spec.default or "")
        return widget
    if kind == "email":
        widget = EmailInput(parent)
        widget.set_email(spec.default or "")
        return widget
    if kind == "rfc":
        widget = TaxIdentifierInput(parent)
        widget.set_value(spec.default or "")
        return widget
    if kind == "check":
        widget = StandardCheckBox(spec.label, parent)
        widget.setChecked(bool(spec.default))
        return widget
    if kind == "customer":
        widget = _CustomerField(customer_provider or (lambda _q: []), parent)
        if spec.default:
            widget.set_value(str(spec.default), spec.default_label)
        return widget
    widget = StandardLineEdit(parent, placeholder=spec.placeholder, required=spec.required)
    if spec.default is not None:
        widget.setText(str(spec.default))
    return widget


def read_input(spec: FieldSpec, widget):
    kind = spec.kind
    if kind == "textarea":
        return widget.value()
    if kind in ("choice", "user"):
        return widget.current_id()
    if kind == "money":
        return widget.decimal_value()
    if kind in ("integer", "percent"):
        return int(widget.value())
    if kind == "date":
        # ``date`` (no texto): el dominio la guarda con ``.isoformat()``.
        return widget.date_value()
    if kind == "datetime":
        # El dominio guarda y compara en UTC con zona (``+00:00``): la hora
        # local sin zona marcaría vencida una actividad horas antes.
        return to_utc_iso(widget.datetime_value())
    if kind == "phone":
        return widget.value() or None
    if kind == "email":
        return widget.email() or None
    if kind == "rfc":
        return widget.value() or None
    if kind == "check":
        return widget.isChecked()
    if kind == "customer":
        return widget.value()
    return widget.text().strip()


def _is_empty(value) -> bool:
    return value is None or (isinstance(value, str) and not value.strip())


class CrmFormDialog(StandardDialog):
    def __init__(self, parent=None, *, title: str, fields: tuple[FieldSpec, ...],
                 submit_text: str = "Guardar", intro: str = "",
                 on_submit: Callable[[dict], object] | None = None,
                 customer_provider=None, user_options=(),
                 width: int = DialogMetrics.WIDTH_MD) -> None:
        super().__init__(parent, title=title, width=width)
        self.setAccessibleName(title)
        self._specs = tuple(fields)
        self._on_submit = on_submit
        self.result_value = None
        if intro:
            text = QLabel(intro, self)
            text.setWordWrap(True)
            text.setProperty("role", "muted")
            self.content_layout().addWidget(text)
        self._form = StandardForm(self)
        self._inputs: dict[str, QWidget] = {}
        for spec in self._specs:
            widget = build_input(spec, self, customer_provider=customer_provider,
                                 user_options=user_options)
            self._inputs[spec.key] = widget
            label = "" if spec.kind == "check" else spec.label
            self._form.add_field(spec.key, FormField(
                label, widget, self, required=spec.required, helper=spec.helper))
        self.content_layout().addWidget(self._form)
        self._error = QLabel("", self)
        self._error.setObjectName("crmFormError")
        self._error.setProperty("state", "ERROR")
        self._error.setWordWrap(True)
        self._error.hide()
        self.content_layout().addWidget(self._error)
        self.add_button_box(ok_text=submit_text, on_accept=self._submit)
        if self._specs:
            first = self._inputs[self._specs[0].key]
            first.setFocus()

    def input(self, key: str):
        return self._inputs.get(key)

    def values(self) -> dict:
        return {spec.key: read_input(spec, self._inputs[spec.key]) for spec in self._specs}

    def _validate(self, values: dict) -> dict[str, str]:
        errors: dict[str, str] = {}
        for spec in self._specs:
            widget = self._inputs[spec.key]
            value = values.get(spec.key)
            if spec.required and _is_empty(value):
                errors[spec.key] = "Este dato es obligatorio."
                continue
            checker = getattr(widget, "is_valid", None)
            if spec.kind in ("phone", "email", "rfc") and callable(checker) and not checker():
                message = getattr(widget, "error_message", lambda: None)()
                errors[spec.key] = message or "El dato no es válido."
        return errors

    def _submit(self) -> None:
        values = self.values()
        errors = self._validate(values)
        self._form.set_errors(errors)
        if errors:
            self._show_error("Revisa los campos marcados.")
            return
        if self._on_submit is None:
            self.result_value = values
            self.accept()
            return
        try:
            result = self._on_submit(values)
        except Exception as exc:  # noqa: BLE001 — el diálogo nunca se cae
            self._show_error(f"No se pudo guardar: {exc}")
            return
        if result is not None and not getattr(result, "success", True):
            self._show_error(getattr(result, "message", "") or "La operación fue rechazada.")
            return
        self.result_value = result
        self.accept()

    def _show_error(self, message: str) -> None:
        self._error.setText(message)
        self._error.show()


def ask(parent, *, title: str, fields: tuple[FieldSpec, ...], submit_text: str = "Guardar",
        intro: str = "", on_submit=None, customer_provider=None, user_options=()):
    """Abre el formulario modal. Devuelve el resultado de ``on_submit`` (o los
    valores si no hay ``on_submit``) cuando se confirmó; ``None`` si se canceló."""
    dialog = CrmFormDialog(parent, title=title, fields=fields, submit_text=submit_text,
                           intro=intro, on_submit=on_submit,
                           customer_provider=customer_provider, user_options=user_options)
    return dialog.result_value if dialog.exec_() else None
