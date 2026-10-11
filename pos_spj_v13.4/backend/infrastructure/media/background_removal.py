"""Quitar el fondo de la foto de un producto, local y sin internet (PROD-21).

Pensado para fotos de catálogo: el producto sobre un fondo más o menos uniforme
(mesa, papel, pared, charola), aunque tenga degradado o sombra suave. Método:

1. El fondo se modela con los colores de los BORDES de la foto: cada borde se
   parte en tramos y se toma la mediana de cada tramo uniforme (un tramo donde
   el producto toca el borde es disparejo y se descarta, para no "comerse" el
   producto).
2. Es candidato a fondo todo pixel cuyo color está cerca de alguno de esos
   colores de referencia (o que ya era transparente).
3. Sólo es fondo el candidato CONECTADO con el borde. Así una etiqueta blanca o
   un brillo dentro del producto no se borra aunque sea del color del fondo.
4. Se limpian motas, se suaviza el contorno (antialias) y se recorta al producto
   con un margen, para que llene la tarjeta del POS.

Si la foto no tiene un fondo distinguible (sin tramos uniformes, o casi todo es
"fondo" o casi nada), se lanza ``ProductImageProcessingError`` con un mensaje que
la pantalla muestra tal cual: falla visible, nunca una imagen rota en silencio.

Es un adaptador intercambiable (puerto ``BackgroundRemover``): un removedor con
IA puede sustituirlo sin tocar casos de uso ni pantallas.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
from PIL import Image, ImageOps, UnidentifiedImageError

from backend.domain.products.exceptions import ProductImageProcessingError

#: Lado máximo con el que se trabaja; una foto de celular (4000 px) se reduce.
MAX_SIDE = 1200
#: Tramos por borde para modelar el fondo (degradados, sombras de esquina).
SEGMENTS_PER_SIDE = 6
#: Dispersión máxima (distancia RGB media a la mediana) de un tramo "uniforme".
UNIFORM_SEGMENT_SPREAD = 22.0


class EdgeConnectedBackgroundRemover:
    def __init__(self, *, tolerance: float | None = None, feather: float = 1.0,
                 crop: bool = True, padding_ratio: float = 0.04,
                 max_side: int = MAX_SIDE) -> None:
        self._tolerance = tolerance
        self._feather = feather
        self._crop = crop
        self._padding_ratio = padding_ratio
        self._max_side = max_side

    def remove_background(self, source_path: str, target_path: str) -> None:
        image = _open_rgba(source_path, self._max_side)
        rgba = np.asarray(image).astype(np.float32)
        alpha = self.compute_alpha(rgba)
        out = np.dstack([rgba[..., :3], alpha]).clip(0, 255).astype(np.uint8)
        result = Image.fromarray(out, "RGBA")
        if self._crop:
            result = _crop_to_content(result, self._padding_ratio)
        target = Path(target_path)
        target.parent.mkdir(parents=True, exist_ok=True)
        result.save(target, "PNG", optimize=True)

    # ── núcleo (sin E/S, testeable con arreglos) ────────────────────────────
    def compute_alpha(self, rgba: np.ndarray) -> np.ndarray:
        """Canal alfa (0-255, float32) para un arreglo HxWx4."""
        from scipy import ndimage

        height, width = rgba.shape[:2]
        if height < 8 or width < 8:
            raise ProductImageProcessingError("La imagen es demasiado pequeña")
        rgb = rgba[..., :3]
        alpha_in = rgba[..., 3]

        references, spread = _background_references(rgb, alpha_in)
        transparent = alpha_in < 16
        if not references and not transparent[_border_mask(height, width)].any():
            raise ProductImageProcessingError(
                "No se detectó un fondo uniforme en los bordes de la foto. "
                "Toma la foto sobre un fondo liso, con el producto completo y "
                "sin que toque las orillas.")

        tolerance = self._tolerance or float(np.clip(26.0 + 2.0 * spread, 24.0, 60.0))
        candidate = transparent.copy()
        for ref in references:
            distance = np.sqrt(((rgb - ref) ** 2).sum(axis=2))
            candidate |= distance <= tolerance

        labels, _count = ndimage.label(candidate)
        border = _border_mask(height, width)
        border_labels = np.unique(labels[border & candidate])
        border_labels = border_labels[border_labels > 0]
        background = np.isin(labels, border_labels)

        foreground = ~background
        foreground = ndimage.binary_opening(foreground, iterations=1)
        foreground = _drop_small_components(foreground, ndimage)
        area = float(height * width)
        fg_ratio = foreground.sum() / area
        if fg_ratio < 0.005:
            raise ProductImageProcessingError(
                "No se distinguió el producto del fondo: el producto y el fondo "
                "tienen colores muy parecidos.")
        if fg_ratio > 0.985:
            raise ProductImageProcessingError(
                "La foto casi no tiene fondo que quitar (el producto llena la imagen).")

        soft = foreground.astype(np.float32)
        if self._feather > 0:
            soft = ndimage.gaussian_filter(soft, sigma=self._feather)
            # El suavizado sólo difumina el contorno; el interior queda opaco.
            soft = np.where(ndimage.binary_erosion(foreground, iterations=2), 1.0, soft)
        return np.minimum(alpha_in, soft * 255.0)


def _open_rgba(source_path: str, max_side: int) -> Image.Image:
    path = Path(source_path)
    if not path.is_file():
        raise ProductImageProcessingError(
            "La imagen original no está en este equipo; vuelve a agregarla.")
    try:
        with Image.open(path) as raw:
            image = ImageOps.exif_transpose(raw).convert("RGBA")
    except (UnidentifiedImageError, OSError) as exc:
        raise ProductImageProcessingError(
            f"El archivo no es una imagen válida: {path.name}") from exc
    if max(image.size) > max_side:
        image.thumbnail((max_side, max_side), Image.LANCZOS)
    return image


def _border_mask(height: int, width: int, thickness: int = 2) -> np.ndarray:
    mask = np.zeros((height, width), dtype=bool)
    mask[:thickness, :] = True
    mask[-thickness:, :] = True
    mask[:, :thickness] = True
    mask[:, -thickness:] = True
    return mask


def _background_references(rgb: np.ndarray, alpha: np.ndarray):
    """Medianas de los tramos uniformes del borde + su dispersión típica."""
    # Cada borde como tira (largo, grosor, canales) para partirla en tramos.
    sides = (
        (rgb[:2, :, :].transpose(1, 0, 2), alpha[:2, :].T),
        (rgb[-2:, :, :].transpose(1, 0, 2), alpha[-2:, :].T),
        (rgb[:, 0:2, :], alpha[:, 0:2]),
        (rgb[:, -2:, :], alpha[:, -2:]),
    )
    references: list[np.ndarray] = []
    spreads: list[float] = []
    for strip, strip_alpha in sides:
        length = strip.shape[0]
        step = max(1, length // SEGMENTS_PER_SIDE)
        for start in range(0, length, step):
            seg = strip[start:start + step].reshape(-1, 3)
            seg_alpha = strip_alpha[start:start + step].reshape(-1)
            seg = seg[seg_alpha >= 16]
            if len(seg) < 4:
                continue
            median = np.median(seg, axis=0)
            spread = float(np.sqrt(((seg - median) ** 2).sum(axis=1)).mean())
            if spread <= UNIFORM_SEGMENT_SPREAD:
                references.append(median)
                spreads.append(spread)
    if not references:
        return [], 0.0
    keep = _dominant_cluster(references)
    unique: list[np.ndarray] = []
    for index in keep:
        ref = references[index]
        if all(np.sqrt(((ref - u) ** 2).sum()) > 6.0 for u in unique):
            unique.append(ref)
    return unique, float(np.median([spreads[i] for i in keep]))


def _dominant_cluster(references: list[np.ndarray], link: float = 32.0) -> list[int]:
    """Índices del grupo de colores de borde más numeroso.

    Los tramos se encadenan si sus colores están a menos de ``link``: un
    degradado de fondo queda en un solo grupo (tramos vecinos parecidos),
    mientras que el color de un producto que toca el borde es un salto y forma
    su propio grupo, minoritario, que se descarta.
    """
    count = len(references)
    group = list(range(count))

    def root(i: int) -> int:
        while group[i] != i:
            group[i] = group[group[i]]
            i = group[i]
        return i

    for i in range(count):
        for j in range(i + 1, count):
            if np.sqrt(((references[i] - references[j]) ** 2).sum()) <= link:
                group[root(i)] = root(j)
    members: dict[int, list[int]] = {}
    for i in range(count):
        members.setdefault(root(i), []).append(i)
    return max(members.values(), key=len)


def _drop_small_components(mask: np.ndarray, ndimage) -> np.ndarray:
    labels, count = ndimage.label(mask)
    if count <= 1:
        return mask
    sizes = ndimage.sum(mask, labels, index=np.arange(1, count + 1))
    keep_from = max(sizes.max() * 0.02, mask.size * 0.0005)
    keep = np.zeros(count + 1, dtype=bool)
    keep[1:] = sizes >= keep_from
    return keep[labels]


def _crop_to_content(image: Image.Image, padding_ratio: float) -> Image.Image:
    bbox = image.getchannel("A").point(lambda a: 255 if a > 8 else 0).getbbox()
    if bbox is None:
        return image
    left, top, right, bottom = bbox
    pad = int(round(max(right - left, bottom - top) * padding_ratio))
    return image.crop((max(0, left - pad), max(0, top - pad),
                       min(image.width, right + pad), min(image.height, bottom + pad)))
