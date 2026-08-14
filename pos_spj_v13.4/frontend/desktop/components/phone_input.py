"""Deprecated phone component wrapper.

PhoneWidget is the official SPJ phone input. This wrapper exists only so older
imports keep working while code migrates to `modulos.spj_phone_widget.PhoneWidget`.

CRM-18: unlike the other specialized inputs this phase wired to the virtual
keyboard (``email_input.py``/``decimal_input.py``/``tax_identifier_input.py``/
``integer_input.py``/``address_input.py``), ``PhoneWidget`` is legacy code in
``modulos/`` (its own inline ``setStyleSheet`` calls already predate the
design system) — attaching ``attach_virtual_keyboard_action`` to its internal
number field would mean editing untested legacy widget internals, out of
proportion for a phase whose own form doesn't strictly need it (phone is
optional on the CRM-18 quick-add form). Documented gap, not silently
dropped: still open for whichever phase migrates ``PhoneWidget`` itself.
"""
from __future__ import annotations

from modulos.spj_phone_widget import PhoneWidget


class PhoneInput(PhoneWidget):
    def __init__(self, parent=None, *, placeholder: str = "+5215512345678") -> None:
        del placeholder
        super().__init__(parent=parent)

    def value(self) -> str:
        return self.get_e164()

    def set_value(self, value: str) -> None:
        self.set_phone(value)

    def is_valid(self) -> bool:
        return bool(self.value().startswith("+") and 8 <= len(self.value()) <= 16)
