"""Commands del contexto de esquemas de despiece (cutting) — capa de aplicación."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class CreateCuttingSchemeCommand:
    operation_id: str
    input_product_id: str
    species_id: str
    name: str
    cut_level: str = "PRIMARY"
    outputs: list[dict] = field(default_factory=list)
    user_id: str | None = None

    def validate(self) -> None:
        missing = [f for f in ("operation_id", "input_product_id", "species_id", "name")
                   if not getattr(self, f)]
        if missing:
            raise ValueError(f"Faltan campos requeridos: {', '.join(missing)}")


@dataclass(frozen=True)
class UpdateCuttingVersionCommand:
    operation_id: str
    version_id: str
    outputs: list[dict] = field(default_factory=list)
    user_id: str | None = None

    def validate(self) -> None:
        missing = [f for f in ("operation_id", "version_id") if not getattr(self, f)]
        if missing:
            raise ValueError(f"Faltan campos requeridos: {', '.join(missing)}")


@dataclass(frozen=True)
class CuttingVersionTransitionCommand:
    operation_id: str
    version_id: str
    user_id: str | None = None
    reason: str | None = None

    def validate(self) -> None:
        missing = [f for f in ("operation_id", "version_id") if not getattr(self, f)]
        if missing:
            raise ValueError(f"Faltan campos requeridos: {', '.join(missing)}")
