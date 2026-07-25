"""Commands del contexto de atributos de producto (P1-03)."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class CreateAttributeCommand:
    operation_id: str
    code: str
    name: str
    data_type: str = "LIST"
    user_id: str | None = None

    def validate(self) -> None:
        missing = [f for f in ("operation_id", "code", "name")
                   if not getattr(self, f)]
        if missing:
            raise ValueError(f"Faltan campos requeridos: {', '.join(missing)}")


@dataclass(frozen=True)
class UpdateAttributeCommand:
    operation_id: str
    attribute_id: str
    code: str
    name: str
    user_id: str | None = None

    def validate(self) -> None:
        missing = [f for f in ("operation_id", "attribute_id", "code", "name")
                   if not getattr(self, f)]
        if missing:
            raise ValueError(f"Faltan campos requeridos: {', '.join(missing)}")


@dataclass(frozen=True)
class SetAttributeActiveCommand:
    operation_id: str
    attribute_id: str
    active: bool
    user_id: str | None = None

    def validate(self) -> None:
        missing = [f for f in ("operation_id", "attribute_id") if not getattr(self, f)]
        if missing:
            raise ValueError(f"Faltan campos requeridos: {', '.join(missing)}")


@dataclass(frozen=True)
class AddAttributeOptionCommand:
    operation_id: str
    attribute_id: str
    code: str
    label: str
    sort_order: int = 0
    user_id: str | None = None

    def validate(self) -> None:
        missing = [f for f in ("operation_id", "attribute_id", "code", "label")
                   if not getattr(self, f)]
        if missing:
            raise ValueError(f"Faltan campos requeridos: {', '.join(missing)}")


@dataclass(frozen=True)
class UpdateAttributeOptionCommand:
    operation_id: str
    option_id: str
    code: str
    label: str
    sort_order: int = 0
    active: bool = True
    user_id: str | None = None

    def validate(self) -> None:
        missing = [f for f in ("operation_id", "option_id", "code", "label")
                   if not getattr(self, f)]
        if missing:
            raise ValueError(f"Faltan campos requeridos: {', '.join(missing)}")
