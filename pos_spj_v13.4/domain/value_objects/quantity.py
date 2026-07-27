# domain/value_objects/quantity.py
from __future__ import annotations
from dataclasses import dataclass

@dataclass(frozen=True)
class Quantity:
    value: float
    unit: str = "pza"

    def __post_init__(self):
        if self.value < 0:
            raise ValueError(f"Cantidad no puede ser negativa: {self.value}")

    def __add__(self, other: "Quantity") -> "Quantity":
        return Quantity(round(self.value + other.value, 4), self.unit)

    def __sub__(self, other: "Quantity") -> "Quantity":
        return Quantity(round(self.value - other.value, 4), self.unit)

    def is_sufficient(self, required: "Quantity") -> bool:
        return self.value >= required.value
