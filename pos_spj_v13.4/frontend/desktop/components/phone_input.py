"""PhoneInput — captura de teléfono en formato E.164.

Antes era una envoltura de `modulos.spj_phone_widget.PhoneWidget`, que
desapareció con la carpeta `modulos/`. No se recupera del historial (§18) ni se
reemplaza por una envoltura de otra cosa: es un componente real, escrito con la
misma forma que sus hermanos del sistema de diseño (`EmailInput`,
`TaxIdentifierInput`, `DecimalInput`) — un `QLineEdit` con accesores de dominio,
validación síncrona y mensaje de error.

QUÉ NORMALIZA Y QUÉ NO
----------------------
Normaliza sólo la PRESENTACIÓN: quita espacios, guiones, puntos y paréntesis,
que es lo que la gente teclea al copiar un número. No adivina el país.

Es deliberado no anteponer un prefijo por omisión a un número nacional de 10
dígitos, por tentador que sea dado que el marcador de posición es mexicano: un
número al que se le pone el país equivocado no falla aquí, falla mucho después
—un WhatsApp que no llega, un reparto que no se puede confirmar— y para
entonces ya está guardado en la ficha del cliente. Si falta el `+`, el campo se
marca inválido y se dice por qué; el país lo pone quien sabe cuál es.

El contrato de validación (prefijo `+`, entre 8 y 16 caracteres) es el que ya
declaraba el `is_valid()` de la envoltura anterior, que sobrevivió a la
eliminación: no es un criterio nuevo.
"""

from __future__ import annotations

import re

from PyQt5.QtCore import pyqtSignal
from PyQt5.QtWidgets import QLineEdit

from frontend.desktop.components.virtual_keyboard import attach_virtual_keyboard_action
from frontend.desktop.themes.tokens import TouchTarget

#: Separadores que la gente teclea y que no forman parte del número.
_SEPARATORS = re.compile(r"[\s\-().]")

#: E.164: `+`, un primer dígito distinto de cero y hasta 15 dígitos en total.
_E164_RE = re.compile(r"^\+[1-9]\d{6,14}$")

#: Límites del contrato heredado, en caracteres incluyendo el `+`.
MIN_LENGTH = 8
MAX_LENGTH = 16


class PhoneInput(QLineEdit):
    value_changed = pyqtSignal()

    def __init__(
        self, parent=None, *, required: bool = False,
        placeholder: str = "+5215512345678",
    ) -> None:
        super().__init__(parent)
        self.setObjectName("phoneInput")
        self._required = required
        self.setPlaceholderText(placeholder)
        self.setMaxLength(MAX_LENGTH)
        self.setMinimumHeight(TouchTarget.INPUT_HEIGHT)
        self.textChanged.connect(lambda _t: self.value_changed.emit())
        attach_virtual_keyboard_action(self)

    def value(self) -> str:
        """El número en E.164, sin separadores. Cadena vacía si está vacío."""
        return _SEPARATORS.sub("", self.text().strip())

    def set_value(self, value: str | None) -> None:
        self.setText(_SEPARATORS.sub("", (value or "").strip()))

    def is_valid(self) -> bool:
        texto = self.value()
        if not texto:
            return not self._required
        return bool(_E164_RE.match(texto)) and MIN_LENGTH <= len(texto) <= MAX_LENGTH

    def error_message(self) -> str | None:
        if self.is_valid():
            return None
        texto = self.value()
        if not texto:
            return "El teléfono es obligatorio."
        if not texto.startswith("+"):
            return "Incluye el código de país, por ejemplo +52 para México."
        return "El teléfono no tiene un formato válido."
