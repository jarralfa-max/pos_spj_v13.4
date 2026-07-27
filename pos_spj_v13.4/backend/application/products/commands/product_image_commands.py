"""Commands de la galería de imágenes de producto (P1)."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class AddProductImageCommand:
    operation_id: str
    product_id: str
    uri: str
    alt_text: str | None = None
    make_primary: bool = False
    user_id: str | None = None

    def validate(self) -> None:
        missing = [f for f in ("operation_id", "product_id", "uri")
                   if not getattr(self, f)]
        if missing:
            raise ValueError(f"Faltan campos requeridos: {', '.join(missing)}")


@dataclass(frozen=True)
class SetPrimaryImageCommand:
    operation_id: str
    image_id: str
    user_id: str | None = None

    def validate(self) -> None:
        missing = [f for f in ("operation_id", "image_id") if not getattr(self, f)]
        if missing:
            raise ValueError(f"Faltan campos requeridos: {', '.join(missing)}")


@dataclass(frozen=True)
class RemoveProductImageCommand:
    operation_id: str
    image_id: str
    user_id: str | None = None

    def validate(self) -> None:
        missing = [f for f in ("operation_id", "image_id") if not getattr(self, f)]
        if missing:
            raise ValueError(f"Faltan campos requeridos: {', '.join(missing)}")
