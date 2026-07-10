# tests/test_logo_quitar_fondo.py
"""Utilidad de logo: quitar_fondo hace transparente el fondo sólido."""
import io

import pytest

pytest.importorskip("PIL")

from PIL import Image  # noqa: E402

from frontend.desktop.components.logo_utils import quitar_fondo  # noqa: E402


def _png_con_fondo(bg=(255, 255, 255), shape=(200, 50, 50), size=40):
    """PNG con fondo sólido y un cuadro de color en el centro."""
    img = Image.new("RGB", (size, size), bg)
    c0, c1 = size // 4, size - size // 4
    for y in range(c0, c1):
        for x in range(c0, c1):
            img.putpixel((x, y), shape)
    buf = io.BytesIO(); img.save(buf, format="PNG")
    return buf.getvalue()


def _abrir(data):
    return Image.open(io.BytesIO(data)).convert("RGBA")


def test_fondo_blanco_se_vuelve_transparente():
    out = quitar_fondo(_png_con_fondo())
    img = _abrir(out)
    w, h = img.size
    # esquinas (fondo) → alfa 0
    for x, y in [(0, 0), (w - 1, 0), (0, h - 1), (w - 1, h - 1)]:
        assert img.getpixel((x, y))[3] == 0
    # centro (forma) → opaco y con el color original
    r, g, b, a = img.getpixel((w // 2, h // 2))
    assert a == 255
    assert (r, g, b) == (200, 50, 50)


def test_es_png_con_alfa():
    out = quitar_fondo(_png_con_fondo())
    img = Image.open(io.BytesIO(out))
    assert img.format == "PNG"
    assert img.mode == "RGBA"


def test_fondo_de_color_no_blanco():
    # fondo verde: también debe volverse transparente (se infiere de las esquinas)
    out = quitar_fondo(_png_con_fondo(bg=(0, 180, 0), shape=(10, 10, 200)))
    img = _abrir(out)
    assert img.getpixel((0, 0))[3] == 0
    assert img.getpixel((img.size[0] // 2, img.size[1] // 2))[3] == 255


def test_region_interior_del_color_del_fondo_se_preserva():
    """Escenario del logo Juanis: fondo casi-blanco con un cuerpo BLANCO interior
    encerrado por un borde oscuro. El flood-fill sólo quita el fondo conectado al
    borde; el interior blanco NO debe volverse transparente (no se hueca el logo)."""
    from PIL import Image, ImageDraw
    size = 60
    img = Image.new("RGB", (size, size), (244, 244, 244))   # fondo gris claro
    d = ImageDraw.Draw(img)
    # anillo/borde oscuro que encierra una zona interior
    d.rectangle([15, 15, 44, 44], outline=(20, 60, 30), width=3)
    # interior BLANCO (mismo tono que podría confundirse con el fondo)
    d.rectangle([19, 19, 40, 40], fill=(255, 255, 255))
    buf = io.BytesIO(); img.save(buf, format="PNG")

    out = quitar_fondo(buf.getvalue(), tolerancia=32)
    res = _abrir(out)
    # esquina (fondo conectado al borde) → transparente
    assert res.getpixel((0, 0))[3] == 0
    # interior blanco encerrado → sigue OPACO (no se elimina)
    assert res.getpixel((size // 2, size // 2))[3] == 255
    # el borde oscuro se conserva opaco
    assert res.getpixel((15, size // 2))[3] == 255 or res.getpixel((size // 2, 15))[3] == 255


def test_datos_no_decodificables_se_devuelven_igual():
    basura = b"<svg>no raster</svg>"
    assert quitar_fondo(basura) == basura


def test_tolerancia_cubre_variacion_leve():
    # fondo casi-blanco con ruido leve dentro de tolerancia
    img = Image.new("RGB", (30, 30), (250, 250, 250))
    img.putpixel((0, 0), (245, 248, 252))
    buf = io.BytesIO(); img.save(buf, format="PNG")
    out = quitar_fondo(buf.getvalue(), tolerancia=30)
    res = _abrir(out)
    assert res.getpixel((0, 0))[3] == 0
