# domain/value_objects/money.py
from __future__ import annotations
from dataclasses import dataclass

@dataclass(frozen=True)
class Money:
    amount: float
    currency: str = "MXN"

    def __add__(self, other: "Money") -> "Money":
        return Money(round(self.amount + other.amount, 2), self.currency)

    def __mul__(self, factor: float) -> "Money":
        return Money(round(self.amount * factor, 2), self.currency)

    def __ge__(self, other: "Money") -> bool:
        return self.amount >= other.amount

    @classmethod
    def zero(cls) -> "Money":
        return cls(0.0)

    def __str__(self) -> str:
        return f"${self.amount:,.2f} {self.currency}"
