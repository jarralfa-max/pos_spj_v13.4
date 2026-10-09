"""Página de prueba de una impresora (Configuración → Dispositivos).

Corta y legible: dice qué dispositivo es, por qué conexión salió y cuándo, para
que quien la sostiene en la mano sepa que imprimió la impresora correcta.
"""

from __future__ import annotations

from datetime import datetime

from backend.infrastructure.printing.escpos import (
    ALIGN_CENTER,
    ALIGN_LEFT,
    BOLD_OFF,
    BOLD_ON,
    CUT_PARTIAL,
    DEFAULT_ENCODING,
    FEED_LINE,
    INIT,
    sanitize_text,
)


def render_diagnostic_page(*, device_code: str, device_name: str, connection: str,
                           paper_width_mm: int, printed_at: datetime) -> bytes:
    ancho = 32 if paper_width_mm <= 58 else 48

    def linea(texto: str) -> bytes:
        return sanitize_text(texto)[:ancho].encode(DEFAULT_ENCODING, errors="replace") + FEED_LINE

    return b"".join((
        INIT, ALIGN_CENTER, BOLD_ON, linea("PRUEBA DE IMPRESION"), BOLD_OFF,
        linea("-" * ancho), ALIGN_LEFT,
        linea(f"Dispositivo: {device_code}"), linea(device_name),
        linea(f"Conexion: {connection}"), linea(f"Papel: {paper_width_mm} mm"),
        linea(f"Fecha: {printed_at:%Y-%m-%d %H:%M}"),
        linea("-" * ancho), ALIGN_CENTER, linea("Si lees esto, la impresora funciona."),
        FEED_LINE * 3, CUT_PARTIAL,
    ))
