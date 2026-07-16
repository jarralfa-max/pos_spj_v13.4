"""Immutable value objects for the HR bounded context."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import time
from decimal import Decimal

from backend.domain.hr.exceptions import HRDomainError

_E164 = re.compile(r"^\+[1-9]\d{7,14}$")
_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


@dataclass(frozen=True, slots=True)
class PhoneE164:
    """Phone number in strict E.164 form (+<country><number>)."""

    value: str

    def __post_init__(self) -> None:
        cleaned = (self.value or "").strip().replace(" ", "")
        if not _E164.match(cleaned):
            raise HRDomainError(f"Teléfono no está en formato E.164: {self.value!r}")
        object.__setattr__(self, "value", cleaned)

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True, slots=True)
class Email:
    value: str

    def __post_init__(self) -> None:
        cleaned = (self.value or "").strip().lower()
        if not _EMAIL.match(cleaned):
            raise HRDomainError(f"Correo inválido: {self.value!r}")
        object.__setattr__(self, "value", cleaned)

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True, slots=True)
class Money:
    """Decimal-backed monetary amount for salaries and payroll (no floats)."""

    amount: Decimal
    currency_code: str = "MXN"

    def __post_init__(self) -> None:
        if isinstance(self.amount, float):
            raise HRDomainError("Money no debe construirse desde float; use str o Decimal")
        if not isinstance(self.amount, Decimal):
            raise HRDomainError(f"Money.amount debe ser Decimal, recibido {type(self.amount).__name__}")
        object.__setattr__(self, "amount", self.amount.quantize(Decimal("0.01")))
        object.__setattr__(self, "currency_code", self.currency_code.upper())

    @classmethod
    def from_string(cls, raw: str, currency_code: str = "MXN") -> "Money":
        from decimal import InvalidOperation
        try:
            return cls(Decimal(str(raw).strip()), currency_code)
        except (InvalidOperation, AttributeError, TypeError) as exc:
            raise HRDomainError(f"Importe inválido: {raw!r}") from exc

    @classmethod
    def zero(cls, currency_code: str = "MXN") -> "Money":
        return cls(Decimal("0"), currency_code)

    def add(self, other: "Money") -> "Money":
        self._same_currency(other)
        return Money(self.amount + other.amount, self.currency_code)

    def subtract(self, other: "Money") -> "Money":
        self._same_currency(other)
        return Money(self.amount - other.amount, self.currency_code)

    def multiply(self, factor: Decimal | int | str) -> "Money":
        if isinstance(factor, float):
            raise HRDomainError("Money.multiply no debe recibir float")
        return Money(self.amount * Decimal(str(factor)), self.currency_code)

    def is_negative(self) -> bool:
        return self.amount < Decimal("0")

    def is_positive(self) -> bool:
        return self.amount > Decimal("0")

    def is_zero(self) -> bool:
        return self.amount == Decimal("0")

    def to_string(self) -> str:
        return format(self.amount, "f")

    def _same_currency(self, other: "Money") -> None:
        if self.currency_code != other.currency_code:
            raise HRDomainError(f"Monedas distintas: {self.currency_code} vs {other.currency_code}")


@dataclass(frozen=True, slots=True)
class TimeRange:
    """A shift time window; may cross midnight (night shifts)."""

    start: time
    end: time

    @property
    def crosses_midnight(self) -> bool:
        return self.end <= self.start

    def duration_minutes(self) -> int:
        start_min = self.start.hour * 60 + self.start.minute
        end_min = self.end.hour * 60 + self.end.minute
        if self.crosses_midnight:
            end_min += 24 * 60
        return end_min - start_min
