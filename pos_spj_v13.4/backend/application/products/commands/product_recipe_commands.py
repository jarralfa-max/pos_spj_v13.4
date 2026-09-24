"""Commands del contexto de recetas de producto (capa de aplicación).

Los componentes/outputs viajan como dicts simples desde la UI; los use cases los
convierten en entidades de dominio (que validan cantidades Decimal, scrap, yield).
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class CreateRecipeCommand:
    operation_id: str
    product_id: str
    recipe_type: str
    name: str
    components: list[dict] = field(default_factory=list)
    outputs: list[dict] = field(default_factory=list)
    user_id: str | None = None

    def validate(self) -> None:
        missing = [f for f in ("operation_id", "product_id", "recipe_type", "name")
                   if not getattr(self, f)]
        if missing:
            raise ValueError(f"Faltan campos requeridos: {', '.join(missing)}")


@dataclass(frozen=True)
class UpdateDraftVersionCommand:
    operation_id: str
    version_id: str
    components: list[dict] = field(default_factory=list)
    outputs: list[dict] = field(default_factory=list)
    user_id: str | None = None

    def validate(self) -> None:
        missing = [f for f in ("operation_id", "version_id") if not getattr(self, f)]
        if missing:
            raise ValueError(f"Faltan campos requeridos: {', '.join(missing)}")


@dataclass(frozen=True)
class RecipeVersionTransitionCommand:
    operation_id: str
    version_id: str
    user_id: str | None = None
    reason: str | None = None

    def validate(self) -> None:
        missing = [f for f in ("operation_id", "version_id") if not getattr(self, f)]
        if missing:
            raise ValueError(f"Faltan campos requeridos: {', '.join(missing)}")
