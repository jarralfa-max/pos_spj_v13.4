"""ESC/POS real para una etiqueta térmica.

Reemplaza lo que probaba contra `core/ticket_escpos_renderer.py`. Se comprueba
el flujo de bytes que sale hacia la impresora, no que se llamó a una función:
una etiqueta mal formada no falla, sale impresa y nadie puede leerla.
"""
from __future__ import annotations

import pytest

from backend.domain.inventory.value_objects.label_document import LabelDocument
from backend.infrastructure.hardware.label_rendering.escpos_label_renderer import (
    render_escpos_label,
)
from backend.infrastructure.printing.escpos import (
    CUT_PARTIAL,
    DOTS_BY_PAPER_WIDTH_MM,
    INIT,
    dots_for_paper_width,
    render_barcode,
    render_qr,
    sanitize_text,
)

RASTER = b"\x1dv0\x00"


def _document(**overrides) -> LabelDocument:
    from backend.domain.inventory.enums import LabelType

    campos = dict(
        label_type=LabelType.PRODUCT, title="Jamón Serrano",
        lines=("Lote L-1", "Cad. 2026-12-01"), barcode="7501234567890",
        qr_payload="https://spj.mx/p/1",
    )
    campos.update(overrides)
    return LabelDocument(**campos)


# ── estructura del flujo ────────────────────────────────────────────────────
def test_the_label_starts_by_resetting_the_printer():
    """Sin `ESC @` la etiqueta hereda el estado de la anterior — negrita o
    alineación pegadas de la impresión previa."""
    assert render_escpos_label(_document(), copies=1).startswith(INIT)


def test_each_copy_ends_with_its_own_cut():
    """Las térmicas de etiqueta no tienen un comando de cantidad como el `^PQ`
    de ZPL: las copias son repetición real del bloque."""
    salida = render_escpos_label(_document(), copies=3)
    assert salida.count(CUT_PARTIAL) == 3


@pytest.mark.parametrize("copies", [0, -1])
def test_a_non_positive_quantity_still_prints_one(copies):
    """Pedir cero etiquetas es un dato mal formado, no una orden de no
    imprimir; imprimir una es preferible a devolver un flujo vacío que la
    impresora ignora sin decir nada."""
    assert render_escpos_label(_document(), copies=copies).count(CUT_PARTIAL) == 1


def test_the_title_and_the_lines_reach_the_stream():
    salida = render_escpos_label(_document(), copies=1)
    assert b"Jamon Serrano" in salida       # saneado: sin tilde, legible
    assert b"Lote L-1" in salida
    assert b"Cad. 2026-12-01" in salida


# ── saneado de texto ────────────────────────────────────────────────────────
def test_accents_are_flattened_not_replaced():
    """"Jamon" se lee; "Jam?n" parece un error de datos."""
    assert sanitize_text("Jamón Serrano") == "Jamon Serrano"
    assert sanitize_text("Piña, Ñandú") == "Pina, Nandu"


def test_control_characters_are_dropped_but_newlines_survive():
    """Un byte de control suelto puede reconfigurar la impresora a media
    etiqueta; el salto de línea es contenido legítimo."""
    assert sanitize_text("a\x00b\x07c") == "abc"
    assert sanitize_text("a\nb") == "a\nb"


def test_unprintable_symbols_do_not_break_the_stream():
    """Un emoji no existe en la página de códigos, pero no puede reventar la
    impresión de la etiqueta entera."""
    assert isinstance(sanitize_text("Oferta 🛍️"), str)


# ── gráficos ────────────────────────────────────────────────────────────────
def test_barcode_and_qr_are_sent_as_raster_blocks():
    salida = render_escpos_label(_document(), copies=1)
    assert salida.count(RASTER) == 2


def test_a_label_without_graphics_has_no_raster_block():
    salida = render_escpos_label(_document(barcode="", qr_payload=""), copies=1)
    assert RASTER not in salida
    assert salida.startswith(INIT) and salida.endswith(CUT_PARTIAL)


def test_an_empty_payload_produces_nothing_rather_than_an_empty_graphic():
    assert render_barcode("", max_width_dots=384) == b""
    assert render_qr("   ", max_width_dots=384) == b""


def test_a_payload_the_symbology_rejects_does_not_break_the_label():
    """La etiqueta sale con su texto, que es lo que identifica el producto."""
    salida = render_escpos_label(_document(barcode="\x01\x02 imposible"), copies=1)
    assert b"Jamon Serrano" in salida
    assert salida.endswith(CUT_PARTIAL)


def test_the_raster_header_declares_width_in_bytes_and_height_in_dots():
    """`GS v 0 m xL xH yL yH`: el ancho va en BYTES. Declararlo en puntos
    multiplicaría por ocho el ancho y la impresora leería como imagen los bytes
    de la siguiente orden."""
    raster = render_qr("https://spj.mx/p/1", max_width_dots=384)
    assert raster.startswith(RASTER)
    ancho_bytes = raster[4] | (raster[5] << 8)
    alto_dots = raster[6] | (raster[7] << 8)
    assert 0 < ancho_bytes <= 384 // 8
    assert len(raster) - 8 == ancho_bytes * alto_dots


def test_a_graphic_never_exceeds_the_paper_width():
    """Más ancho que el papel no da error: la impresora lo recorta por la
    derecha y el código sale ilegible a medias."""
    raster = render_qr("x" * 400, max_width_dots=384)
    if raster:
        assert (raster[4] | (raster[5] << 8)) <= 384 // 8


# ── ancho de papel ──────────────────────────────────────────────────────────
@pytest.mark.parametrize("mm, dots", sorted(DOTS_BY_PAPER_WIDTH_MM.items()))
def test_known_paper_widths_map_to_their_dot_count(mm, dots):
    assert dots_for_paper_width(mm) == dots


def test_an_unknown_paper_width_falls_back_to_the_narrowest():
    """Pasarse de ancho recorta contenido; quedarse corto sólo deja margen."""
    assert dots_for_paper_width(999) == DOTS_BY_PAPER_WIDTH_MM[58]
