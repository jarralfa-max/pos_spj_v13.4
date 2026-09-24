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

from frontend.desktop.components.address_input import AddressInput
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
#: "Contado"/"Crédito" se traduce a la bandera `PaymentTerms.is_credit`; los
#: ids de este combo son sólo de la pantalla.
_PAYMENT_MODES = [("CASH_ON_DELIVERY", "Contado"), ("CREDIT", "Crédito")]
#: Sólo las formas que el negocio usa (decisión del usuario, 2026-09-17).
_PAYMENT_METHODS = [("TRANSFER", "Transferencia (SPEI)"), ("CASH", "Efectivo")]
_ADDRESS_TYPES = [
    ("FISCAL", "Fiscal"), ("BILLING", "Facturación"), ("SHIPPING", "Envío"),
    ("WAREHOUSE", "Almacén"), ("PICKUP", "Recolección"), ("OFFICE", "Oficina"),
    ("OTHER", "Otro"),
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
        # WhatsApp con el MISMO componente que el teléfono: es E.164 igual que
        # él (regla §19), y capturarlo como texto libre dejaría entrar números
        # que el canal de WhatsApp luego no puede usar.
        self._whatsapp = PhoneInput()
        self._email = EmailInput()
        self._primary = QCheckBox("Contacto principal")
        self.form.addRow("Nombre *", self._name)
        self.form.addRow("Área", self._type)
        self.form.addRow("Cargo", self._role)
        self.form.addRow("Teléfono", self._phone)
        self.form.addRow("WhatsApp", self._whatsapp)
        self.form.addRow("Correo", self._email)
        self.form.addRow("", self._primary)

    def _error(self) -> str | None:
        if not self._name.value():
            return "El nombre es obligatorio."
        if self._type.current_id() is None:
            return "Selecciona el área del contacto."
        # El teléfono NO se validaba (sólo el correo). Se valida ahora junto con
        # WhatsApp: `PhoneInput.is_valid()` acepta vacío cuando no es
        # obligatorio, así que nada de lo que hoy se guarda deja de ser válido —
        # sólo deja de aceptarse un número mal formado.
        if not self._phone.is_valid():
            return "El teléfono debe estar en formato internacional (+52...)."
        if not self._whatsapp.is_valid():
            return "El WhatsApp debe estar en formato internacional (+52...)."
        if not self._email.is_valid():
            return "El correo no tiene un formato válido."
        return None

    def values(self) -> dict:
        return {
            "name": self._name.value(), "contact_type": self._type.current_id(),
            "role": self._role.value(),
            "phone_e164": self._phone.value() or None,
            "whatsapp_e164": self._whatsapp.value() or None,
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
        self._payment_mode = _combo(_PAYMENT_MODES)
        self._payment_method = _combo(_PAYMENT_METHODS)
        self._credit_days = IntegerInput(minimum=0, maximum=365)
        self._credit_limit = MoneyInput()
        self._advance_required = QCheckBox("Requiere anticipo")
        self._advance_pct = PercentInput()
        self._lead_time = IntegerInput(minimum=0, maximum=365)
        self._window = TimeRangeInput()
        self._window.set_range("08:00", "16:00")
        self.form.addRow("Tipo de pago *", self._payment_mode)
        self.form.addRow("Forma de pago preferida", self._payment_method)
        self.form.addRow("Días de crédito", self._credit_days)
        self.form.addRow("Límite de crédito", self._credit_limit)
        self.form.addRow("", self._advance_required)
        self.form.addRow("Anticipo (%)", self._advance_pct)
        self.form.addRow("Lead time (días)", self._lead_time)
        self.form.addRow("Ventana de recepción", self._window)

    def _error(self) -> str | None:
        mode = self._payment_mode.current_id()
        if mode is None:
            return "Indica si el proveedor es de contado o de crédito."
        if mode == "CREDIT" and self._credit_days.value() <= 0:
            return "Un proveedor a crédito necesita días de crédito mayores a cero."
        if mode == "CASH_ON_DELIVERY" and self._credit_days.value() > 0:
            return "Un proveedor de contado no puede tener días de crédito."
        window_error = self._window.validate()
        if window_error:
            return window_error
        if self._advance_required.isChecked() and self._advance_pct.decimal_value() <= 0:
            return "El anticipo requerido necesita un porcentaje mayor a cero."
        return None

    def values(self) -> dict:
        return {
            "is_credit": self._payment_mode.current_id() == "CREDIT",
            "preferred_payment_method": self._payment_method.current_id(),
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


class SupplierReasonDialog(_SupplierDialog):
    """Motivo obligatorio para suspender o dar de baja.

    Existe uno equivalente en el módulo de Compras, pero importarlo desde aquí
    acoplaría dos módulos de UI por un formulario de tres líneas; éste reusa la
    base y la validación que ya tiene este módulo.
    """

    dialog_title = "Motivo"

    def __init__(self, parent=None, *, title: str = "Motivo",
                 placeholder: str = "Motivo (obligatorio)") -> None:
        self.dialog_title = title
        self._placeholder = placeholder
        super().__init__(parent)

    def _build(self) -> None:
        self._reason = StandardTextArea(placeholder=self._placeholder)
        self.form.addRow("Motivo *", self._reason)

    def _error(self) -> str | None:
        if not self._reason.value():
            return "El motivo es obligatorio."
        return None

    def reason(self) -> str:
        return self._reason.value()

    def values(self) -> dict:
        return {"reason": self.reason()}


class SupplierAddressDialog(_SupplierDialog):
    """Domicilio del proveedor, con el componente estándar de dirección.

    Eran cinco cajas de texto libre. Ahora es `AddressInput`: búsqueda con
    Mapbox (o Nominatim de respaldo) desde el 5.º carácter y captura manual en
    los mismos campos. Las columnas `latitude`, `longitude`, `geocoding_source`
    y `validation_state` existían en `supplier_addresses` desde el esquema
    original y NUNCA se llenaban: no había por dónde capturarlas.
    """

    dialog_title = "Nuevo domicilio"

    def __init__(self, parent=None, *, search_service=None, runner=None) -> None:
        # Antes de `super().__init__`, que es quien llama a `_build`.
        self._search_service = search_service
        self._runner = runner
        super().__init__(parent, width=DialogMetrics.WIDTH_LG)

    def _build(self) -> None:
        self._type = _combo(_ADDRESS_TYPES)
        self._address = AddressInput(self, search_service=self._search_service,
                                     runner=self._runner)
        self.form.addRow("Tipo *", self._type)
        self.form.addRow("Domicilio *", self._address)

    def _error(self) -> str | None:
        if self._type.current_id() is None:
            return "Selecciona el tipo de domicilio."
        if not self._address.value().street_line():
            return "La calle y número son obligatorios."
        return None

    def values(self) -> dict:
        direccion = self._address.value()
        # `SupplierAddress` no tiene columna de colonia: se antepone a la línea
        # para no perder el dato mientras el dominio no la modele.
        line = direccion.street_line()
        if direccion.neighborhood:
            line = f"{line}, Col. {direccion.neighborhood}"
        return {
            "address_type": self._type.current_id(),
            "line": line,
            "city": direccion.municipality, "state": direccion.state,
            "postal_code": direccion.postal_code,
            "country_code": direccion.country_code,
            "latitude": direccion.latitude if direccion.is_geocoded else None,
            "longitude": direccion.longitude if direccion.is_geocoded else None,
            "geocoding_source": direccion.source.value if direccion.is_geocoded else None,
            "validation_state": "GEOCODED" if direccion.is_geocoded else "MANUAL",
        }


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
