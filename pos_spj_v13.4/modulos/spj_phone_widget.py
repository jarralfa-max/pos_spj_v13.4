# modulos/spj_phone_widget.py — SPJ POS v13.2
"""
Widget reutilizable de captura de teléfono.
Formato: [+52 ▼] [número sin código]

USO:
    from modulos.spj_phone_widget import PhoneWidget

    self.phone = PhoneWidget()           # default +52 México
    self.phone.set_phone("+5215551234567")   # carga un número completo
    numero = self.phone.get_e164()       # "+5215551234567"
    local  = self.phone.get_number()     # "15551234567"
    codigo = self.phone.get_country_code() # "+52"
"""

from PyQt5.QtWidgets import (
    QWidget, QHBoxLayout, QComboBox, QLineEdit, QLabel
)
from PyQt5.QtCore import pyqtSignal
from PyQt5.QtGui import QRegExpValidator
from PyQt5.QtCore import QRegExp


# Países más comunes en LATAM + internacionales frecuentes
COUNTRY_CODES = [
    ("+52",  "🇲🇽 MX"),
    ("+1",   "🇺🇸 US/CA"),
    ("+502", "🇬🇹 GT"),
    ("+503", "🇸🇻 SV"),
    ("+504", "🇭🇳 HN"),
    ("+505", "🇳🇮 NI"),
    ("+506", "🇨🇷 CR"),
    ("+507", "🇵🇦 PA"),
    ("+53",  "🇨🇺 CU"),
    ("+57",  "🇨🇴 CO"),
    ("+58",  "🇻🇪 VE"),
    ("+51",  "🇵🇪 PE"),
    ("+593", "🇪🇨 EC"),
    ("+591", "🇧🇴 BO"),
    ("+56",  "🇨🇱 CL"),
    ("+595", "🇵🇾 PY"),
    ("+598", "🇺🇾 UY"),
    ("+54",  "🇦🇷 AR"),
    ("+55",  "🇧🇷 BR"),
    ("+34",  "🇪🇸 ES"),
    ("+1",   "🌐 Otro"),
]


class PhoneWidget(QWidget):
    """
    Widget compuesto: selector de código de país + campo de número.
    Emite `changed` cuando el usuario edita cualquiera de los dos campos.
    """
    changed = pyqtSignal(str)   # emite el número E.164 completo

    def __init__(self, default_country: str = "+52", parent=None):
        super().__init__(parent)
        self._build_ui(default_country)

    def _build_ui(self, default_country: str) -> None:
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(4)

        # Selector de código de país
        self.cmb_code = QComboBox()
        self.cmb_code.setFixedWidth(105)
        # v13.30: Sin colores hardcoded — hereda del tema global
        self.cmb_code.setStyleSheet(
            "QComboBox { padding:4px 6px; border-radius:4px; }"
            "QComboBox::drop-down { border:none; }"
        )
        seen = set()
        default_idx = 0
        for i, (code, label) in enumerate(COUNTRY_CODES):
            key = f"{code}_{label}"
            if key in seen:
                continue
            seen.add(key)
            self.cmb_code.addItem(f"{label} {code}", code)
            if code == default_country and label not in ("🌐 Otro",):
                default_idx = self.cmb_code.count() - 1
        self.cmb_code.setCurrentIndex(default_idx)

        # Campo de número (solo dígitos - 10 dígitos estrictos para México)
        self.txt_number = QLineEdit()
        self.txt_number.setPlaceholderText("5512345678 (10 dígitos)")
        self.txt_number.setToolTip("Captura solo los 10 dígitos del número. El código +52 se agrega automáticamente.")
        # v13.30: Sin colores hardcoded — hereda del tema global
        self.txt_number.setStyleSheet(
            "QLineEdit { padding:4px 8px; border-radius:4px; }"
        )
        # VALIDACIÓN ESTRICTA: Solo 10 dígitos para números de México (+52)
        validator = QRegExpValidator(QRegExp(r"\d{10}"))
        self.txt_number.setValidator(validator)
        self.txt_number.setMaxLength(10)

        lay.addWidget(self.cmb_code)
        lay.addWidget(self.txt_number, 1)

        self.cmb_code.currentIndexChanged.connect(self._emit)
        self.txt_number.textChanged.connect(self._emit)

    def _emit(self) -> None:
        self.changed.emit(self.get_e164())

    # ── Public API ────────────────────────────────────────────────────────────

    def get_country_code(self) -> str:
        """Retorna el código seleccionado, ej: '+52'"""
        return self.cmb_code.currentData() or "+52"

    def get_number(self) -> str:
        """Retorna solo los dígitos del número sin el código."""
        return self.txt_number.text().strip()

    def get_e164(self) -> str:
        """
        Retorna el número completo en formato E.164: '+521234567890'.
        Si el campo está vacío retorna ''.
        """
        num = self.get_number().replace(" ", "").replace("-", "").replace("(","").replace(")","")
        if not num:
            return ""
        code = self.get_country_code()
        return f"{code}{num}"

    def set_phone(self, full_number: str) -> None:
        """
        Carga un número completo (E.164 o solo dígitos).
        Detecta el código de país automáticamente.
        """
        if not full_number:
            self.txt_number.clear()
            return

        full = full_number.strip()
        if not full.startswith("+"):
            # Número sin código — asumir el código seleccionado
            self.txt_number.setText(full)
            return

        # Intentar detectar el código
        matched_code = "+52"
        matched_rest = full[1:]  # sin el '+'
        # Sort by length desc so longer codes match first (e.g. +502 before +50)
        sorted_codes = sorted(set(c for c, _ in COUNTRY_CODES), key=len, reverse=True)
        for code in sorted_codes:
            if full.startswith(code):
                matched_code = code
                matched_rest = full[len(code):]
                break

        # Select matching country in combobox
        for i in range(self.cmb_code.count()):
            if self.cmb_code.itemData(i) == matched_code:
                self.cmb_code.setCurrentIndex(i)
                break

        self.txt_number.setText(matched_rest)

    def set_enabled(self, enabled: bool) -> None:
        self.cmb_code.setEnabled(enabled)
        self.txt_number.setEnabled(enabled)

    def clear(self) -> None:
        self.txt_number.clear()

    # ── Proxy methods — make PhoneWidget behave like QLineEdit for callers ──
    def setPlaceholderText(self, text: str) -> None:
        """Proxy: sets placeholder on the number field."""
        self.txt_number.setPlaceholderText(text)

    def setText(self, text: str) -> None:
        """Proxy: loads a full phone number (same as set_phone)."""
        self.set_phone(text)

    def text(self) -> str:
        """Proxy: returns E.164 number (same as get_e164)."""
        return self.get_e164()

    def setToolTip(self, tip: str) -> None:
        self.txt_number.setToolTip(tip)
        super().setToolTip(tip)

    def setReadOnly(self, ro: bool) -> None:
        self.txt_number.setReadOnly(ro)
        self.cmb_code.setEnabled(not ro)

    def setInputMask(self, mask: str) -> None:
        """Proxy: apply input mask to number field (or ignore — PhoneWidget validates internally)."""
        # Input masks for phone numbers don't apply well to international format
        # so we silently ignore them — PhoneWidget handles its own validation
        pass

    def setMaxLength(self, length: int) -> None:
        self.txt_number.setMaxLength(length)

    def setMinimumWidth(self, w: int) -> None:
        super().setMinimumWidth(w)

    def setFixedWidth(self, w: int) -> None:
        super().setFixedWidth(w)

    def setStyleSheet(self, style: str) -> None:
        """Proxy: apply stylesheet to number field."""
        self.txt_number.setStyleSheet(style)

    def setFont(self, font) -> None:
        self.txt_number.setFont(font)
        self.cmb_code.setFont(font)

    def setObjectName(self, name: str) -> None:
        super().setObjectName(name)
        self.txt_number.setObjectName(name + "_number")

    def is_valid(self) -> bool:
        """True si el número tiene exactamente 10 dígitos (formato México +52)."""
        digits = "".join(c for c in self.get_number() if c.isdigit())
        return len(digits) == 10
