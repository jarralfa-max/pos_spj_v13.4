"""ProductAttribute + AttributeOption — atributos configurables (P1-03).

Un atributo define un eje de clasificación/variación (p. ej. Color, Talla). Los de
tipo ``LIST`` llevan opciones enumeradas; el resto captura texto/número/booleano
libre en la asignación del producto. Identidad UUIDv7; sin precio ni existencia.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

from backend.domain.products.exceptions import (
    AttributeOptionNotAllowedError,
    InvalidAttributeError,
)
from backend.shared.ids import new_uuid


class AttributeDataType(str, Enum):
    LIST = "LIST"
    TEXT = "TEXT"
    NUMBER = "NUMBER"
    BOOLEAN = "BOOLEAN"


def normalize_name(name: str) -> str:
    return " ".join(str(name or "").strip().lower().split())


@dataclass
class ProductAttribute:
    code: str
    name: str
    id: str = field(default_factory=new_uuid)
    data_type: AttributeDataType = AttributeDataType.LIST
    active: bool = True

    def __post_init__(self) -> None:
        code = (self.code or "").strip().upper()
        if not code:
            raise InvalidAttributeError("El atributo requiere un código")
        if not (self.name or "").strip():
            raise InvalidAttributeError("El atributo requiere un nombre")
        if not isinstance(self.data_type, AttributeDataType):
            try:
                object.__setattr__(self, "data_type",
                                   AttributeDataType(str(self.data_type)))
            except ValueError as exc:
                raise InvalidAttributeError(
                    f"Tipo de atributo inválido: {self.data_type}") from exc
        object.__setattr__(self, "code", code)
        object.__setattr__(self, "name", (self.name or "").strip())

    @property
    def name_normalized(self) -> str:
        return normalize_name(self.name)

    @property
    def is_list(self) -> bool:
        return self.data_type == AttributeDataType.LIST

    def ensure_accepts_options(self) -> None:
        if not self.is_list:
            raise AttributeOptionNotAllowedError(
                "Sólo los atributos de tipo LISTA admiten opciones enumeradas")


@dataclass
class AttributeOption:
    attribute_id: str
    code: str
    label: str
    id: str = field(default_factory=new_uuid)
    sort_order: int = 0
    active: bool = True

    def __post_init__(self) -> None:
        if not (self.attribute_id or "").strip():
            raise InvalidAttributeError("La opción requiere un atributo")
        code = (self.code or "").strip().upper()
        if not code:
            raise InvalidAttributeError("La opción requiere un código")
        if not (self.label or "").strip():
            raise InvalidAttributeError("La opción requiere una etiqueta")
        object.__setattr__(self, "code", code)
        object.__setattr__(self, "label", (self.label or "").strip())
