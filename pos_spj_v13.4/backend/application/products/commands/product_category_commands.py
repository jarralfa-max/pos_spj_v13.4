"""Commands del contexto de categorías de producto (P1-01)."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class CreateCategoryCommand:
    operation_id: str
    code: str
    name: str
    user_id: str | None = None
    parent_id: str | None = None
    sort_order: int = 0

    def validate(self) -> None:
        missing = [f for f in ("operation_id", "code", "name")
                   if not getattr(self, f)]
        if missing:
            raise ValueError(f"Faltan campos requeridos: {', '.join(missing)}")


@dataclass(frozen=True)
class UpdateCategoryCommand:
    operation_id: str
    category_id: str
    code: str
    name: str
    user_id: str | None = None
    sort_order: int = 0

    def validate(self) -> None:
        missing = [f for f in ("operation_id", "category_id", "code", "name")
                   if not getattr(self, f)]
        if missing:
            raise ValueError(f"Faltan campos requeridos: {', '.join(missing)}")


@dataclass(frozen=True)
class MoveCategoryCommand:
    operation_id: str
    category_id: str
    new_parent_id: str | None
    user_id: str | None = None

    def validate(self) -> None:
        missing = [f for f in ("operation_id", "category_id") if not getattr(self, f)]
        if missing:
            raise ValueError(f"Faltan campos requeridos: {', '.join(missing)}")


@dataclass(frozen=True)
class SetCategoryActiveCommand:
    operation_id: str
    category_id: str
    active: bool
    user_id: str | None = None

    def validate(self) -> None:
        missing = [f for f in ("operation_id", "category_id") if not getattr(self, f)]
        if missing:
            raise ValueError(f"Faltan campos requeridos: {', '.join(missing)}")
