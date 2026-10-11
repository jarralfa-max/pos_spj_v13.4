"""Puertos de imágenes de producto (PROD-21).

Los casos de uso de la galería no conocen Pillow ni el disco: reciben estos dos
contratos. Las implementaciones viven en ``backend/infrastructure/media/``.
Ambos lanzan ``ProductImageProcessingError`` cuando el archivo no sirve, para que
el caso de uso pueda explicarlo en pantalla en vez de reventar.
"""

from __future__ import annotations

from typing import Protocol


class ProductImageStorage(Protocol):
    def import_original(self, source_path: str) -> str:
        """Copia (y normaliza) el archivo elegido a la carpeta de la aplicación.
        Devuelve la referencia que se guarda en ``product_images.uri``."""

    def new_processed_path(self) -> str:
        """Ruta destino para una versión procesada (PNG con transparencia)."""

    def is_local_file(self, uri: str) -> bool:
        """El archivo existe en este equipo y se puede leer."""

    def discard(self, uri: str | None) -> None:
        """Borra el archivo SÓLO si vive en la carpeta administrada."""


class BackgroundRemover(Protocol):
    def remove_background(self, source_path: str, target_path: str) -> None:
        """Escribe en ``target_path`` un PNG con el fondo transparente."""
