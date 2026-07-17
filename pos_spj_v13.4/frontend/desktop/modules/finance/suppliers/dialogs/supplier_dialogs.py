"""Supplier form dialogs — capture only, validated, Design System inputs.

No SQL, no business rules: they gather input and hand a dict to the presenter.
Specialized inputs are mandatory (TaxIdentifierInput/PhoneInput/EmailInput/
MoneyInput/PercentInput/TimeRangeInput/…), never a raw QLineEdit for those data.
"""

from __future__ import annotations

from decimal import Decimal

from PyQt5.QtWidgets import (
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QMessageBox,
    QVBoxLayout,
)

from frontend.desktop.components import (
    EmailInput,
    IntegerInput,
    MoneyInput,
    MonthInput,
    PercentInput,
    PhoneInput,
    SearchableComboBox,
    StandardLineEdit,
    StandardTextArea,
    TaxIdentifierInput,
    TimeRangeInput,
)
from frontend.desktop.i18n.es_mx import ui
from frontend.desktop.themes.tokens import DialogMetrics, Spacing

_CLASSIFICATIONS = [
    ("GOODS", "Bienes"), ("SERVICES", "Servicios"), ("LOGISTICS", "Logística"),
    ("MAINTENANCE", "Mantenimiento"), ("PROFESSIONAL_SERVICES", "Servicios profesionales"),
    ("ASSETS", "Activos"), ("TECHNOLOGY", "Tecnología"), ("OTHER", "Otro"),
]
_COMMERCIAL = [
    ("POULTRY", "Pollo"), ("EGGS", "Huevo"), ("GROCERIES", "Abarrotes"),
    ("PACKAGING", "Empaques"), ("DISPOSABLES", "Desechables"), ("CLEANING", "Limpieza"),
    ("TRANSPORT", "Transporte"), ("EQUIPMENT", "Equipo"),
]
_CONTACT_TYPES = [
    ("PURCHASING", "Compras"), ("SALES", "Ventas"), ("BILLING", "Facturación"),
    ("COLLECTIONS", "Cobranza"), ("LOGISTICS", "Logística"), ("QUALITY", "Calidad"),
    ("MANAGEMENT", "Gerencia"), ("EMERGENCY", "Emergencias"),
]
_BLOCK_TYPES = [
    ("PURCHASING_BLOCK", "Compras"), ("PAYMENT_BLOCK", "Pagos"),
    ("RECEIVING_BLOCK", "Recepción"), ("QUALITY_BLOCK", "Calidad"),
    ("GENERAL_BLOCK", "General"),
]
_EVAL_DIMENSIONS = [
    ("QUALITY", "Calidad"), ("ON_TIME_DELIVERY", "Entrega a tiempo"),
    ("COMPLETE_QUANTITY", "Cantidad completa"), ("PRICE", "Precio"),
    ("SERVICE", "Servicio"),
]


class _SupplierDialog(QDialog):
    dialog_title = ""

    def __init__(self, parent=None, *, width: int = DialogMetrics.WIDTH_MD) -> None:
        super().__init__(parent)
        self.setObjectName("standardDialog")
        self.setWindowTitle(self.dialog_title)
        self.setMinimumWidth(width)
        root = QVBoxLayout(self)
        root.setContentsMargins(DialogMetrics.PADDING, DialogMetrics.PADDING,
                                DialogMetrics.PADDING, DialogMetrics.PADDING)
        root.setSpacing(Spacing.MD)
        self.form = QFormLayout()
        self.form.setSpacing(Spacing.SM)
        root.addLayout(self.form)
        self._build()
        box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel, self)
        box.button(QDialogButtonBox.Ok).setText(ui("action.save"))
        box.button(QDialogButtonBox.Cancel).setText(ui("action.cancel"))
        box.accepted.connect(self._accept_if_valid)
        box.rejected.connect(self.reject)
        root.addWidget(box)

    def _build(self) -> None:
        raise NotImplementedError

    def _error(self) -> str | None:
        return None

    def values(self) -> dict:
        raise NotImplementedError

    def _accept_if_valid(self) -> None:
        error = self._error()
        if error:
            QMessageBox.warning(self, self.dialog_title, error)
            return
        self.accept()


def _combo(options) -> SearchableComboBox:
    combo = SearchableComboBox()
    combo.set_options(options)
    return combo


class SupplierFormDialog(_SupplierDialog):
    dialog_title = "Nuevo proveedor"

    def _build(self) -> None:
        self._legal = StandardLineEdit(placeholder="Razón social", required=True)
        self._trade = StandardLineEdit(placeholder="Nombre comercial")
        self._rfc = TaxIdentifierInput(kind="RFC", required=True)
        self._classification = _combo(_CLASSIFICATIONS)
        self._category = _combo(_COMMERCIAL)
        self._currency = _combo([("MXN", "MXN"), ("USD", "USD")])
        self._currency.set_current_id("MXN")
        self._notes = StandardTextArea(placeholder="Notas")
        self.form.addRow("Razón social *", self._legal)
        self.form.addRow("Nombre comercial", self._trade)
        self.form.addRow("RFC *", self._rfc)
        self.form.addRow("Clasificación", self._classification)
        self.form.addRow("Categoría comercial", self._category)
        self.form.addRow("Moneda preferida", self._currency)
        self.form.addRow("Notas", self._notes)

    def _error(self) -> str | None:
        if not self._legal.value():
            return "La razón social es obligatoria."
        if not self._rfc.is_valid():
            return "El RFC no tiene un formato válido."
        return None

    def values(self) -> dict:
        classifications = [self._classification.current_id()] if self._classification.has_selection() else []
        categories = [self._category.current_id()] if self._category.has_selection() else []
        return {
            "legal_name": self._legal.value(),
            "trade_name": self._trade.value(),
            "tax_identifier": self._rfc.value(),
            "preferred_currency": self._currency.current_id() or "MXN",
            "classifications": classifications,
            "categories": categories,
        }


class SupplierContactDialog(_SupplierDialog):
    dialog_title = "Nuevo contacto"

    def _build(self) -> None:
        self._name = StandardLineEdit(placeholder="Nombre", required=True)
        self._type = _combo(_CONTACT_TYPES)
        self._role = StandardLineEdit(placeholder="Cargo")
        self._phone = PhoneInput()
        self._email = EmailInput()
        self._primary = QCheckBox("Contacto principal")
        self.form.addRow("Nombre *", self._name)
        self.form.addRow("Área", self._type)
        self.form.addRow("Cargo", self._role)
        self.form.addRow("Teléfono", self._phone)
        self.form.addRow("Correo", self._email)
        self.form.addRow("", self._primary)

    def _error(self) -> str | None:
        if not self._name.value():
            return "El nombre es obligatorio."
        if self._type.current_id() is None:
            return "Selecciona el área del contacto."
        if not self._email.is_valid():
            return "El correo no tiene un formato válido."
        return None

    def values(self) -> dict:
        return {
            "name": self._name.value(), "contact_type": self._type.current_id(),
            "role": self._role.value(),
            "phone_e164": self._phone.get_e164() if hasattr(self._phone, "get_e164") else None,
            "email": self._email.email() or None, "is_primary": self._primary.isChecked(),
        }


class SupplierBankAccountDialog(_SupplierDialog):
    dialog_title = "Nueva cuenta bancaria"

    def _build(self) -> None:
        self._bank = StandardLineEdit(placeholder="Banco", required=True)
        self._holder = StandardLineEdit(placeholder="Titular", required=True)
        self._clabe = StandardLineEdit(placeholder="CLABE (18 dígitos)")
        self._account = StandardLineEdit(placeholder="Número de cuenta")
        self._currency = _combo([("MXN", "MXN"), ("USD", "USD")])
        self._currency.set_current_id("MXN")
        self.form.addRow("Banco *", self._bank)
        self.form.addRow("Titular *", self._holder)
        self.form.addRow("CLABE", self._clabe)
        self.form.addRow("Cuenta", self._account)
        self.form.addRow("Moneda", self._currency)

    def _error(self) -> str | None:
        if not self._bank.value() or not self._holder.value():
            return "Banco y titular son obligatorios."
        clabe = "".join(ch for ch in self._clabe.value() if ch.isdigit())
        if clabe and len(clabe) != 18:
            return "La CLABE debe tener 18 dígitos."
        return None

    def values(self) -> dict:
        return {
            "bank_name": self._bank.value(), "account_holder": self._holder.value(),
            "clabe": self._clabe.value(), "account_number": self._account.value(),
            "currency_code": self._currency.current_id() or "MXN",
        }


class SupplierTermsDialog(_SupplierDialog):
    dialog_title = "Condiciones comerciales"

    def _build(self) -> None:
        self._credit_days = IntegerInput(minimum=0, maximum=365)
        self._credit_limit = MoneyInput()
        self._advance_required = QCheckBox("Requiere anticipo")
        self._advance_pct = PercentInput()
        self._lead_time = IntegerInput(minimum=0, maximum=365)
        self._window = TimeRangeInput()
        self._window.set_range("08:00", "16:00")
        self.form.addRow("Días de crédito", self._credit_days)
        self.form.addRow("Límite de crédito", self._credit_limit)
        self.form.addRow("", self._advance_required)
        self.form.addRow("Anticipo (%)", self._advance_pct)
        self.form.addRow("Lead time (días)", self._lead_time)
        self.form.addRow("Ventana de recepción", self._window)

    def _error(self) -> str | None:
        window_error = self._window.validate()
        if window_error:
            return window_error
        if self._advance_required.isChecked() and self._advance_pct.decimal_value() <= 0:
            return "El anticipo requerido necesita un porcentaje mayor a cero."
        return None

    def values(self) -> dict:
        return {
            "credit_days": self._credit_days.value(),
            "credit_limit": str(self._credit_limit.decimal_value()),
            "advance_required": self._advance_required.isChecked(),
            "advance_percentage": str(self._advance_pct.decimal_value()),
            "lead_time_days": self._lead_time.value(),
            "receiving_window_start": self._window.start_text(),
            "receiving_window_end": self._window.end_text(),
        }


class SupplierBlockDialog(_SupplierDialog):
    dialog_title = "Bloquear proveedor"

    def _build(self) -> None:
        self._type = _combo(_BLOCK_TYPES)
        self._reason = StandardTextArea(placeholder="Motivo del bloqueo")
        self.form.addRow("Tipo de bloqueo", self._type)
        self.form.addRow("Motivo *", self._reason)

    def _error(self) -> str | None:
        if self._type.current_id() is None:
            return "Selecciona el tipo de bloqueo."
        if not self._reason.value():
            return "El bloqueo requiere un motivo."
        return None

    def values(self) -> dict:
        return {"block_type": self._type.current_id(), "reason": self._reason.value()}


class SupplierEvaluationDialog(_SupplierDialog):
    dialog_title = "Evaluar proveedor"

    def _build(self) -> None:
        self._period = MonthInput()
        self._scores = {}
        self.form.addRow("Periodo", self._period)
        for code, label in _EVAL_DIMENSIONS:
            spin = IntegerInput(minimum=0, maximum=100)
            self._scores[code] = spin
            self.form.addRow(label, spin)
        self._comments = StandardTextArea(placeholder="Comentarios")
        self.form.addRow("Comentarios", self._comments)

    def values(self) -> dict:
        return {
            "period": self._period.month_text(),
            "items": [{"dimension": code, "score": spin.value()}
                      for code, spin in self._scores.items()],
            "comments": self._comments.value(),
        }
