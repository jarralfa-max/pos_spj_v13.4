"""Prohibido escpos.printer.Usb como ruta default de impresión en Windows.

La ruta canónica es PrinterService → transporte (USB_WIN32 vía win32print,
NETWORK, SERIAL, FILE). escpos.Usb (libusb) solo puede usarse como fallback
no-Windows explícito, nunca desde la UI.
"""

from __future__ import annotations

import re

from .architecture_guardrails import APP_ROOT, PYTHON_SUFFIXES, collect_regex_violations, iter_files

#: Tambien la forma con varios nombres —`from escpos.printer import Network, Usb`—,
#: que la version anterior no veia porque exigia `Usb` justo tras `import`.
#: La importacion entre parentesis repartida en varias lineas sigue fuera de
#: alcance: el recorrido es linea a linea.
ESC_POS_USB_RE = re.compile(
    r"from\s+escpos\.printer\s+import\s+[^\n#]*\bUsb\b|escpos\.printer\.Usb")

#: Donde viven HOY la UI y la aplicacion.
#:
#: Antes eran `modulos/`, `interfaz/`, `presentation/`, `application/` y
#: `backend/`. Las cuatro primeras se borraron, y como `iter_files` salta las
#: raices inexistentes, la guardia llevaba sin leer UNA SOLA linea de interfaz:
#: la regla existe precisamente para la UI y solo miraba `backend/`.
#: `frontend/` cubre escritorio y web.
UI_AND_SERVICES = (
    APP_ROOT / "frontend",
    APP_ROOT / "backend",
)


def test_no_escpos_usb_in_ui_or_application() -> None:
    """Ni la UI ni la aplicacion importan `escpos.printer.Usb`.

    Antes de buscar se exige que cada raiz APORTE archivos: sin eso, una ruta
    renombrada o borrada deja la prueba en verde leyendo cero lineas, que es
    como esta guardia dejo de vigilar la interfaz sin que nada fallara.

    La capa de hardware (`backend/infrastructure/printing`, `.../hardware`) NO
    se excluye, aunque el contrato permita alli el fallback no-Windows. Hoy
    ningun archivo del proyecto importa `escpos` —la impresion usa su propio
    `backend/infrastructure/printing/escpos.py`—, asi que el primer uso tiene
    que ser un cambio deliberado de esta guardia, no algo que pase solo.
    """
    vacias = [r.relative_to(APP_ROOT).as_posix() for r in UI_AND_SERVICES
              if not any(True for _ in iter_files(suffixes=PYTHON_SUFFIXES, roots=(r,)))]
    assert not vacias, (
        "Raices que no aportan ningun archivo; la prueba pasaria sin leerlas:\n  "
        + "\n  ".join(vacias))

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
