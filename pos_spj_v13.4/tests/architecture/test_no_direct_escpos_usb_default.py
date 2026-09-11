"""Prohibido escpos.printer.Usb como ruta default de impresión en Windows.

La ruta canónica es PrinterService → transporte (USB_WIN32 vía win32print,
NETWORK, SERIAL, FILE). escpos.Usb (libusb) solo puede usarse como fallback
no-Windows explícito, nunca desde la UI.
"""

from __future__ import annotations

import re

from .architecture_guardrails import APP_ROOT, collect_regex_violations

ESC_POS_USB_RE = re.compile(r"from\s+escpos\.printer\s+import\s+Usb|escpos\.printer\.Usb")

UI_AND_SERVICES = (
    APP_ROOT / "modulos",
    APP_ROOT / "interfaz",
    APP_ROOT / "presentation",
    APP_ROOT / "application",
    APP_ROOT / "backend",
)


def test_no_escpos_usb_in_ui_or_application() -> None:
    violations = collect_regex_violations(pattern=ESC_POS_USB_RE, roots=UI_AND_SERVICES)
    assert not violations, (
        "escpos.printer.Usb usado fuera de la capa de hardware:\n"
        + "\n".join(f"{v.relative_path}:{v.line_number}: {v.text}" for v in violations)
    )


def test_usb_default_transport_is_win32_on_windows() -> None:
    """El transporte USB por omisión en Windows es win32print, no libusb.

    Antes se comprobaba sobre `core/services/hardware_service.py`, que ya no
    existe. El guardrail no se retira por eso: apunta ahora al transporte
    canónico vivo, que es donde hoy podría invertirse la preferencia.
    """
    path = APP_ROOT / "backend" / "infrastructure" / "printing" / "transport.py"
    text = path.read_text(encoding="utf-8")
    assert "_send_win32" in text, (
        "PrintTransport debe exponer `_send_win32` para la ruta USB en Windows")
    assert "win32print" in text, (
        "la ruta USB de Windows debe ir por win32print, no por libusb")
