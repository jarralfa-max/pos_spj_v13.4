"""Vista previa de un ticket ESC/POS: interpreta los BYTES que se enviarían a la
impresora y los dibuja (comparativa main ↔ ERP, 2026-10-16: «preview del mismo
renderer»).

No es un emulador general de impresoras: entiende exactamente el subconjunto de
comandos que emiten `ticket_layout_renderer` y `escpos` (inicializar,
alineación, negritas, doble tamaño, imagen rasterizada `GS v 0`, corte, saltos
de línea y texto cp437). Un comando desconocido se ignora y se reporta, para
que una vista previa nunca muestre algo distinto en silencio.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from backend.infrastructure.printing.escpos import DEFAULT_ENCODING, dots_for_paper_width

COLUMNS = {58: 32, 80: 48}
_FONTS = ("consola.ttf", "DejaVuSansMono.ttf", "cour.ttf", "LiberationMono-Regular.ttf")


@dataclass
class PreviewResult:
    image: object                      # PIL.Image
    unknown_commands: list[str] = field(default_factory=list)
    cut: bool = False


def _font(cell_width: int):
    from PIL import ImageFont
    for name in _FONTS:
        for size in range(cell_width * 2, 6, -1):
            try:
                font = ImageFont.truetype(name, size)
            except OSError:
                break
            if font.getlength("M") <= cell_width:
                return font
    return ImageFont.load_default()


def render_preview(data: bytes, *, paper_width_mm: int = 80,
                   encoding: str = DEFAULT_ENCODING) -> PreviewResult:
    from PIL import Image, ImageDraw

    dots = dots_for_paper_width(paper_width_mm)
    columns = COLUMNS.get(paper_width_mm, 48)
    cell = dots // columns
    font = _font(cell)
    line_height = int(cell * 2.0)
    margin = 8

    rows: list[tuple] = []   # ("text", str, align, bold, scale) | ("image", PIL, align)
    unknown: list[str] = []
    align, bold, scale, buffer, cut = 0, False, 1, bytearray(), False

    def flush() -> None:
        rows.append(("text", buffer.decode(encoding, errors="replace"), align, bold, scale))
        buffer.clear()

    i, n = 0, len(data)
    while i < n:
        b = data[i]
        if b == 0x0A:
            flush()
            i += 1
        elif b == 0x1B and i + 1 < n:
            cmd = data[i + 1]
            if cmd == 0x40:                              # ESC @
                align, bold, scale = 0, False, 1
                i += 2
            elif cmd == 0x61 and i + 2 < n:              # ESC a n
                align = data[i + 2] % 3
                i += 3
            elif cmd == 0x45 and i + 2 < n:              # ESC E n
                bold = bool(data[i + 2])
                i += 3
            else:
                unknown.append(f"ESC {cmd:#04x}")
                i += 2
        elif b == 0x1D and i + 1 < n:
            cmd = data[i + 1]
            if cmd == 0x56:                              # GS V A n — corte
                cut = True
                i += 4 if i + 2 < n and data[i + 2] in (0x41, 0x42) else 3
            elif cmd == 0x21 and i + 2 < n:              # GS ! n — tamaño
                scale = 2 if data[i + 2] else 1
                i += 3
            elif cmd == 0x76 and i + 7 < n:              # GS v 0 m xL xH yL yH
                width_bytes = data[i + 4] | (data[i + 5] << 8)
                height = data[i + 6] | (data[i + 7] << 8)
                start = i + 8
                raw = data[start:start + width_bytes * height]
                if buffer:
                    flush()
                image = Image.new("1", (width_bytes * 8, height), 1)
                pixels = image.load()
                for y in range(height):
                    for xb in range(width_bytes):
                        byte = raw[y * width_bytes + xb] if y * width_bytes + xb < len(raw) else 0
                        for bit in range(8):
                            if byte & (0x80 >> bit):
                                pixels[xb * 8 + bit, y] = 0
                rows.append(("image", image, align))
                i = start + width_bytes * height
            else:
                unknown.append(f"GS {cmd:#04x}")
                i += 2
        else:
            buffer.append(b)
            i += 1
    if buffer:
        flush()

    height = margin * 2
    for row in rows:
        height += row[1].height if row[0] == "image" else line_height * row[4]
    canvas = Image.new("L", (dots + margin * 2, max(height, 40)), 255)
    draw = ImageDraw.Draw(canvas)
    y = margin
    for row in rows:
        if row[0] == "image":
            image, row_align = row[1], row[2]
            x = margin + (0 if row_align == 0 else (dots - image.width) // (2 if row_align == 1 else 1))
            canvas.paste(image.convert("L"), (max(margin, x), y))
            y += image.height
            continue
        _, text, row_align, row_bold, row_scale = row
        text_width = font.getlength(text) * row_scale
        x = margin + (0 if row_align == 0 else
                      int((dots - text_width) // (2 if row_align == 1 else 1)))
        if row_scale == 1:
            draw.text((x, y), text, fill=0, font=font)
            if row_bold:
                draw.text((x + 1, y), text, fill=0, font=font)
        else:
            tile = Image.new("L", (max(1, int(font.getlength(text)) + 2), line_height), 255)
            tile_draw = ImageDraw.Draw(tile)
            tile_draw.text((0, 0), text, fill=0, font=font)
            if row_bold:
                tile_draw.text((1, 0), text, fill=0, font=font)
            tile = tile.resize((tile.width * 2, tile.height * 2))
            canvas.paste(tile, (max(margin, x), y))
        y += line_height * row_scale
    return PreviewResult(canvas, unknown, cut)
