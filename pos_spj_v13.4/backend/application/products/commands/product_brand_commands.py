"""Commands del contexto de marcas de producto (P1-02)."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class CreateBrandCommand:
    operation_id: str
    code: str
    name: str
    user_id: str | None = None
    description: str | None = None

    def validate(self) -> None:
        missing = [f for f in ("operation_id", "code", "name")
                   if not getattr(self, f)]
        if missing:
            raise ValueError(f"Faltan campos requeridos: {', '.join(missing)}")


@dataclass(frozen=True)
class UpdateBrandCommand:
    operation_id: str
    brand_id: str
    code: str
    name: str
    user_id: str | None = None
    description: str | None = None

    def validate(self) -> None:
        missing = [f for f in ("operation_id", "brand_id", "code", "name")
                   if not getattr(self, f)]
        if missing:
            raise ValueError(f"Faltan campos requeridos: {', '.join(missing)}")


@dataclass(frozen=True)
class SetBrandActiveCommand:
    operation_id: str
    brand_id: str
    active: bool
    user_id: str | None = None

    def validate(self) -> None:
        missing = [f for f in ("operation_id", "brand_id") if not getattr(self, f)]
        if missing:
            raise ValueError(f"Faltan campos requeridos: {', '.join(missing)}")
