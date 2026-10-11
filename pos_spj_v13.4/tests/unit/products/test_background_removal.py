"""PROD-21 — removedor de fondo local (`EdgeConnectedBackgroundRemover`).

Imágenes sintéticas con geometría conocida: se verifica qué queda transparente,
qué queda opaco y que una foto sin fondo distinguible falla con un mensaje que la
pantalla puede mostrar (nunca una imagen rota en silencio).
"""

from __future__ import annotations

import numpy as np
import pytest
from PIL import Image, ImageDraw, ImageFilter

from backend.domain.products.exceptions import ProductImageProcessingError
from backend.infrastructure.media.background_removal import EdgeConnectedBackgroundRemover


def _save(img: Image.Image, path) -> str:
    img.save(path, quality=88)
    return str(path)


def _alpha(path) -> np.ndarray:
    with Image.open(path) as out:
        assert out.mode == "RGBA"
        return np.asarray(out)[..., 3]


def test_plain_background_becomes_transparent_and_product_stays_opaque(tmp_path):
    img = Image.new("RGB", (400, 300), (245, 245, 245))
    ImageDraw.Draw(img).ellipse((100, 50, 300, 250), fill=(170, 40, 40))
    src = _save(img.filter(ImageFilter.GaussianBlur(0.8)), tmp_path / "a.jpg")
    out = tmp_path / "a.png"
    EdgeConnectedBackgroundRemover(crop=False).remove_background(src, str(out))
    alpha = _alpha(out)
    assert alpha[0, 0] == 0 and alpha[-1, -1] == 0          # esquinas: fondo
    assert alpha[150, 200] == 255                            # centro: producto


def test_background_coloured_area_inside_the_product_is_kept(tmp_path):
    """Una etiqueta blanca DENTRO del producto no está conectada al borde."""
    img = Image.new("RGB", (400, 300), (245, 245, 245))
    draw = ImageDraw.Draw(img)
    draw.ellipse((100, 50, 300, 250), fill=(170, 40, 40))
    draw.rectangle((170, 130, 230, 170), fill=(245, 245, 245))
    src = _save(img, tmp_path / "label.png")
    out = tmp_path / "label_out.png"
    EdgeConnectedBackgroundRemover(crop=False).remove_background(src, str(out))
    assert _alpha(out)[150, 200] == 255


def test_result_is_cropped_to_the_product(tmp_path):
    img = Image.new("RGB", (800, 600), (250, 250, 250))
    ImageDraw.Draw(img).rectangle((300, 200, 500, 400), fill=(40, 90, 160))
    src = _save(img, tmp_path / "crop.png")
    out = tmp_path / "crop_out.png"
    EdgeConnectedBackgroundRemover().remove_background(src, str(out))
    with Image.open(out) as result:
        assert result.width < 300 and result.height < 300


def test_gradient_background_is_removed(tmp_path):
    arr = np.zeros((300, 400, 3), np.uint8)
    for y in range(300):
        arr[y, :, :] = (200 + y * 40 // 300, 190 + y * 40 // 300, 170 + y * 40 // 300)
    img = Image.fromarray(arr)
    ImageDraw.Draw(img).rounded_rectangle((140, 80, 260, 220), 15, fill=(120, 70, 40))
    src = _save(img, tmp_path / "grad.png")
    out = tmp_path / "grad_out.png"
    EdgeConnectedBackgroundRemover(crop=False).remove_background(src, str(out))
    alpha = _alpha(out)
    assert alpha[0, 0] == 0 and alpha[-1, 0] == 0
    assert alpha[150, 200] == 255


def test_product_touching_the_border_is_not_eaten(tmp_path):
    """Los tramos del borde con el color del producto son minoría y se descartan."""
    img = Image.new("RGB", (400, 300), (250, 250, 250))
    ImageDraw.Draw(img).rectangle((120, 100, 280, 300), fill=(40, 90, 160))
    src = _save(img, tmp_path / "touch.png")
    out = tmp_path / "touch_out.png"
    EdgeConnectedBackgroundRemover(crop=False).remove_background(src, str(out))
    alpha = _alpha(out)
    assert alpha[200, 200] == 255 and alpha[0, 0] == 0


def test_busy_background_fails_with_a_readable_message(tmp_path):
    rng = np.random.default_rng(7)
    src = _save(Image.fromarray(rng.integers(0, 255, (200, 200, 3), dtype=np.uint8)),
                tmp_path / "noise.png")
    with pytest.raises(ProductImageProcessingError, match="fondo"):
        EdgeConnectedBackgroundRemover().remove_background(src, str(tmp_path / "x.png"))
    assert not (tmp_path / "x.png").exists()


def test_not_an_image_fails(tmp_path):
    bogus = tmp_path / "nota.png"
    bogus.write_bytes(b"esto no es una imagen")
    with pytest.raises(ProductImageProcessingError, match="no es una imagen"):
        EdgeConnectedBackgroundRemover().remove_background(str(bogus), str(tmp_path / "o.png"))


def test_missing_file_fails(tmp_path):
    with pytest.raises(ProductImageProcessingError, match="no está en este equipo"):
        EdgeConnectedBackgroundRemover().remove_background(
            str(tmp_path / "nope.jpg"), str(tmp_path / "o.png"))
