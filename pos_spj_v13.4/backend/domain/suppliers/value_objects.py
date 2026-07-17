"""Value objects for the suppliers bounded context (immutable, self-validating)."""

from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

from backend.domain.suppliers.enums import PersonType, RatingGrade
from backend.domain.suppliers.exceptions import (
    InvalidCommercialTermsError,
    InvalidSupplierCodeError,
    InvalidTaxIdentifierError,
)

_CODE_RE = re.compile(r"^PRV-\d{6,}$")
_RFC_RE = re.compile(r"^[A-ZÑ&]{3,4}\d{6}[A-Z0-9]{3}$")


@dataclass(frozen=True, slots=True)
class SupplierCode:
    value: str

    def __post_init__(self) -> None:
        if not _CODE_RE.match(self.value or ""):
            raise InvalidSupplierCodeError(f"Código inválido: {self.value!r} (usa PRV-NNNNNN)")

    @classmethod
    def from_sequence(cls, sequence: int) -> "SupplierCode":
        return cls(f"PRV-{int(sequence):06d}")

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True, slots=True)
class TaxIdentifier:
    value: str
    country_code: str = "MX"

    def __post_init__(self) -> None:
        normalized = (self.value or "").strip().upper()
        object.__setattr__(self, "value", normalized)
        if self.country_code == "MX" and normalized and not _RFC_RE.match(normalized):
            raise InvalidTaxIdentifierError(f"RFC inválido: {self.value!r}")

    @property
    def person_type(self) -> PersonType | None:
        if self.country_code != "MX" or not self.value:
            return None
        letters = len(re.match(r"^[A-ZÑ&]+", self.value).group(0))
        return PersonType.MORAL if letters == 3 else PersonType.FISICA

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True, slots=True)
class Money:
    amount: Decimal
    currency_code: str = "MXN"

    def __post_init__(self) -> None:
        if isinstance(self.amount, float):
            raise InvalidCommercialTermsError("Money no acepta float; usa Decimal/str")
        try:
            object.__setattr__(self, "amount", Decimal(str(self.amount)))
        except (InvalidOperation, ValueError):
            raise InvalidCommercialTermsError(f"Monto inválido: {self.amount!r}")

    @classmethod
    def zero(cls, currency_code: str = "MXN") -> "Money":
        return cls(Decimal("0"), currency_code)

    def is_negative(self) -> bool:
        return self.amount < 0

    def to_string(self) -> str:
        return f"{self.amount.quantize(Decimal('0.01'))}"


@dataclass(frozen=True, slots=True)
class LeadTime:
    days: int

    def __post_init__(self) -> None:
        if self.days < 0:
            raise InvalidCommercialTermsError("El lead time no puede ser negativo")


@dataclass(frozen=True, slots=True)
class PaymentTerms:
    credit_days: int = 0
    credit_limit: Money = None  # type: ignore[assignment]
    advance_required: bool = False
    advance_percentage: Decimal = Decimal("0")
    prompt_payment_discount: Decimal = Decimal("0")
    min_order_amount: Money = None  # type: ignore[assignment]
    quantity_tolerance: Decimal = Decimal("0")
    price_tolerance: Decimal = Decimal("0")

    def __post_init__(self) -> None:
        if self.credit_days < 0:
            raise InvalidCommercialTermsError("Los días de crédito no pueden ser negativos")
        for name in ("advance_percentage", "prompt_payment_discount"):
            value = Decimal(str(getattr(self, name)))
            object.__setattr__(self, name, value)
            if not (Decimal("0") <= value <= Decimal("100")):
                raise InvalidCommercialTermsError(f"{name} debe estar entre 0 y 100")
        if self.credit_limit is None:
            object.__setattr__(self, "credit_limit", Money.zero())
        if self.min_order_amount is None:
            object.__setattr__(self, "min_order_amount", Money.zero())
        if self.advance_required and self.advance_percentage <= 0:
            raise InvalidCommercialTermsError(
                "El anticipo requerido necesita un porcentaje mayor a cero")


@dataclass(frozen=True, slots=True)
class RatingBands:
    """Configurable score→grade thresholds (A/B/C/D)."""

    a_min: int = 90
    b_min: int = 80
    c_min: int = 70

    def grade_for(self, score: int) -> RatingGrade:
        if score >= self.a_min:
            return RatingGrade.A
        if score >= self.b_min:
            return RatingGrade.B
        if score >= self.c_min:
            return RatingGrade.C
        return RatingGrade.D


@dataclass(frozen=True, slots=True)
class SupplierRating:
    score: int
    grade: RatingGrade

    @classmethod
    def from_score(cls, score: int, bands: RatingBands | None = None) -> "SupplierRating":
        score = max(0, min(100, int(score)))
        bands = bands or RatingBands()
        return cls(score=score, grade=bands.grade_for(score))
