"""Commands del contexto de rendimientos (yields) — capa de aplicación.

Los outputs viajan como dicts desde la UI; los use cases los convierten en entidades
``YieldOutput`` (que validan porcentajes/decimales).
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class CreateYieldProfileCommand:
    operation_id: str
    input_product_id: str
    name: str
    species_id: str | None = None
    tolerance_pct: str = "0"
    outputs: list[dict] = field(default_factory=list)
    user_id: str | None = None

    def validate(self) -> None:
        missing = [f for f in ("operation_id", "input_product_id", "name")
                   if not getattr(self, f)]
        if missing:
            raise ValueError(f"Faltan campos requeridos: {', '.join(missing)}")


@dataclass(frozen=True)
class UpdateYieldVersionCommand:
    operation_id: str
    version_id: str
    tolerance_pct: str = "0"
    outputs: list[dict] = field(default_factory=list)
    user_id: str | None = None

    def validate(self) -> None:
        missing = [f for f in ("operation_id", "version_id") if not getattr(self, f)]
        if missing:
            raise ValueError(f"Faltan campos requeridos: {', '.join(missing)}")


@dataclass(frozen=True)
class YieldVersionTransitionCommand:
    operation_id: str
    version_id: str
    user_id: str | None = None
    reason: str | None = None

    def validate(self) -> None:
        missing = [f for f in ("operation_id", "version_id") if not getattr(self, f)]
        if missing:
            raise ValueError(f"Faltan campos requeridos: {', '.join(missing)}")
