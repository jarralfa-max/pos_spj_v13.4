"""Comandos ESC/POS y rasterizado para impresoras térmicas.

Reemplaza lo que `core/ticket_escpos_renderer.py` ofrecía y que se fue con la
carpeta `core/`. No se recuperó del historial (§18): ESC/POS es un estándar de
Epson y sus secuencias de control son públicas, así que las constantes se
escriben desde la especificación, no se copian de ningún sitio.

DOS DIFERENCIAS CON LO QUE REEMPLAZA
------------------------------------
1. Funciones PÚBLICAS. El renderizador de etiquetas llamaba a
   `_sanitize_text()`, `_render_code39_as_image()` y `_render_qr()` — métodos
   privados de otra clase. Una API privada usada desde fuera no es privada: es
   una API sin contrato que nadie sabe que no puede cambiar.

2. Simbología del código de barras: **Code 128**. La clase anterior tenía un
   método llamado `_render_code39_as_image` mientras su propio docstring decía
   "Code-128", así que no hay forma de saber cuál imprimía de verdad. Se elige
   128 porque es lo que emite el renderizador ZPL hermano (`^BC`) para la misma
   `LabelDocument`: dos formatos distintos para la misma etiqueta según la
   impresora sería una diferencia invisible hasta que alguien compara dos
   etiquetas del mismo producto. Ambas codifican el mismo texto, así que un
   lector devuelve lo mismo; cambia la densidad y el juego de caracteres.

SI FALTA UNA DEPENDENCIA NO SE IMPRIME BASURA. `barcode` y `qrcode` son
opcionales; sin ellas, las funciones de rasterizado devuelven vacío y la
etiqueta sale con su texto pero sin el gráfico. Es preferible a una etiqueta con
un rectángulo negro que ningún lector reconoce.
"""

from __future__ import annotations

import io
import logging
import unicodedata

logger = logging.getLogger("spj.printing.escpos")

# ── Comandos (Epson ESC/POS) ─────────────────────────────────────────────────
INIT = b"\x1b@"                 # ESC @  — reinicia la impresora
ALIGN_LEFT = b"\x1ba\x00"       # ESC a 0
ALIGN_CENTER = b"\x1ba\x01"     # ESC a 1
ALIGN_RIGHT = b"\x1ba\x02"      # ESC a 2
BOLD_ON = b"\x1bE\x01"          # ESC E 1
BOLD_OFF = b"\x1bE\x00"         # ESC E 0
CUT_PARTIAL = b"\x1dVA\x00"     # GS V A 0 — corte parcial
FEED_LINE = b"\n"

#: Página de códigos por omisión. `cp437` es la que traen de fábrica casi todas
#: las térmicas; escribir UTF-8 directamente sale como símbolos sueltos.
DEFAULT_ENCODING = "cp437"

#: Anchos de papel habituales, en puntos (203 ppp).
DOTS_BY_PAPER_WIDTH_MM = {58: 384, 80: 576}


def sanitize_text(value: str, *, encoding: str = DEFAULT_ENCODING) -> str:
    """Deja el texto imprimible en una térmica.

    Los acentos se descomponen y se les quita la tilde en vez de sustituirlos
    por `?`: "Jamón" sale "Jamon", que se lee; con la sustitución saldría
    "Jam?n", que parece un error de datos. Lo que aun así no exista en la
    página de códigos se reemplaza, pero ya son casos raros (emoji).
    """
    texto = "".join(ch for ch in str(value or "") if ch == "\n" or ch >= " ")
    plano = unicodedata.normalize("NFKD", texto)
    plano = "".join(ch for ch in plano if not unicodedata.combining(ch))
    return plano.encode(encoding, errors="replace").decode(encoding)


def raster_image(image, *, max_width_dots: int) -> bytes:
    """Convierte una imagen PIL en un bloque `GS v 0` (imagen de trama).

    Formato: `GS v 0 m xL xH yL yH d1...dk`, donde el ancho va en BYTES y el
    alto en puntos. Cada bit es un punto y el bit más significativo es el de la
    izquierda; un 1 imprime.

    Se escala si hace falta: una imagen más ancha que el papel no da error, la
    impresora la recorta por la derecha y el código sale ilegible a medias.
    """
    try:
        from PIL import Image
    except ImportError:
        logger.warning("PIL no está disponible: no se rasteriza la imagen")
        return b""

    if image.width > max_width_dots:
        alto = max(1, int(image.height * max_width_dots / image.width))
        image = image.resize((max_width_dots, alto), Image.LANCZOS)

    # "1" = un bit por píxel. El 0 es negro en PIL, así que se invierte al
    # componer los bytes: en ESC/POS el 1 es el que imprime.
    bitmap = image.convert("1")
    ancho_bytes = (bitmap.width + 7) // 8
    pixels = bitmap.load()

    datos = bytearray()
    for y in range(bitmap.height):
        for byte_index in range(ancho_bytes):
            byte = 0
            for bit in range(8):
                x = byte_index * 8 + bit
                if x < bitmap.width and pixels[x, y] == 0:
                    byte |= 0x80 >> bit
            datos.append(byte)

    return (b"\x1dv0\x00"
            + bytes([ancho_bytes & 0xFF, (ancho_bytes >> 8) & 0xFF])
            + bytes([bitmap.height & 0xFF, (bitmap.height >> 8) & 0xFF])
            + bytes(datos))


def render_barcode(payload: str, *, max_width_dots: int) -> bytes:
    """Code 128 rasterizado. Vacío si no se puede generar."""
    if not str(payload or "").strip():
        return b""
    try:
        import barcode
        from barcode.writer import ImageWriter
    except ImportError:
        logger.warning("La librería `barcode` no está disponible: etiqueta sin código")
        return b""
    try:
        buffer = io.BytesIO()
        barcode.get("code128", str(payload), writer=ImageWriter()).write(
            buffer, options={"write_text": False, "quiet_zone": 2.0})
        buffer.seek(0)
        from PIL import Image

        with Image.open(buffer) as image:
            return raster_image(image, max_width_dots=max_width_dots)
    except Exception as exc:
        # Un payload que la simbología no admite no debe tumbar la impresión
        # entera: la etiqueta sale con su texto, que es lo que identifica el
        # producto.
        logger.warning("No se pudo generar el código de barras %r: %s", payload, exc)
        return b""


def render_qr(payload: str, *, max_width_dots: int) -> bytes:
    """QR rasterizado. Vacío si no se puede generar."""
    if not str(payload or "").strip():
        return b""
    try:
        import qrcode
    except ImportError:
        logger.warning("La librería `qrcode` no está disponible: etiqueta sin QR")
        return b""
    try:
        code = qrcode.QRCode(box_size=4, border=2)
        code.add_data(str(payload))
        code.make(fit=True)
        return raster_image(code.make_image(fill_color="black", back_color="white").convert("1"),
                            max_width_dots=max_width_dots)
    except Exception as exc:
        logger.warning("No se pudo generar el QR %r: %s", payload, exc)
        return b""


def dots_for_paper_width(paper_width_mm: int) -> int:
    """Puntos imprimibles de un ancho de papel.

    Un ancho desconocido cae al de 58 mm, el más estrecho de los habituales:
    pasarse de ancho recorta el contenido, quedarse corto sólo deja margen.
    """
    return DOTS_BY_PAPER_WIDTH_MM.get(int(paper_width_mm), DOTS_BY_PAPER_WIDTH_MM[58])
