"""Impuestos configurables (§22): código, tasa con vigencia, regla y perfil contable.

Ningún porcentaje fiscal vive en código, UI ni casos de uso: la tasa se lee de
``TaxRate`` vigente a la fecha de la operación. Esta arquitectura PREPARA la
integración fiscal (CFDI emitidos/recibidos, complementos de pago); no afirma
cumplimiento fiscal completo — eso exige un módulo fiscal validado.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from decimal import Decimal

from backend.domain.finance.enums import TaxDirection, TaxKind
from backend.domain.finance.exceptions import FinanceDomainError, InvalidMoneyError
from backend.domain.finance.value_objects.money import Money
from backend.shared.ids import new_uuid

#: Alcances de una regla, del más específico al más general.
TAX_RULE_SCOPES = ("PRODUCT", "CATEGORY", "CHANNEL", "DEFAULT")


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass(slots=True)
class TaxCode:
    id: str
    code: str
    name: str
    kind: TaxKind
    direction: TaxDirection
    active: bool = True
    created_at: str = field(default_factory=_utcnow)

    @classmethod
    def create(cls, code: str, name: str, kind: TaxKind,
               direction: TaxDirection) -> "TaxCode":
        code = (code or "").strip().upper()
        if not code or not (name or "").strip():
            raise FinanceDomainError("El impuesto requiere código y nombre")
        return cls(id=new_uuid(), code=code, name=name.strip(), kind=kind,
                   direction=direction)


@dataclass(slots=True)
class TaxRate:
    """Tasa vigente de un código (porcentaje, p. ej. ``16`` o ``0``)."""

    id: str
    tax_code_id: str
    rate_percent: Decimal
    effective_from: date
    effective_to: date | None = None
    created_at: str = field(default_factory=_utcnow)

    @classmethod
    def create(cls, tax_code_id: str, rate_percent: Decimal | str, effective_from: date,
               effective_to: date | None = None) -> "TaxRate":
        if isinstance(rate_percent, float):
            raise InvalidMoneyError("La tasa no se captura como float")
        value = Decimal(str(rate_percent))
        if value < 0 or value > 100:
            raise FinanceDomainError("La tasa de impuesto va de 0 a 100 %")
        if effective_to is not None and effective_to < effective_from:
            raise FinanceDomainError("La vigencia termina antes de empezar")
        return cls(id=new_uuid(), tax_code_id=tax_code_id, rate_percent=value,
                   effective_from=effective_from, effective_to=effective_to)

    def applies_on(self, on_date: date) -> bool:
        return self.effective_from <= on_date and (
            self.effective_to is None or on_date <= self.effective_to)


@dataclass(slots=True)
class TaxRule:
    """Qué código aplica a qué: producto, categoría, canal o por omisión."""

    id: str
    tax_code_id: str
    scope: str
    scope_id: str | None
    effective_from: date
    effective_to: date | None = None
    active: bool = True
    created_at: str = field(default_factory=_utcnow)

    @classmethod
    def create(cls, tax_code_id: str, scope: str, scope_id: str | None,
               effective_from: date, effective_to: date | None = None) -> "TaxRule":
        scope = (scope or "").strip().upper()
        if scope not in TAX_RULE_SCOPES:
            raise FinanceDomainError(f"Alcance de regla inválido: {scope}")
        if scope != "DEFAULT" and not scope_id:
            raise FinanceDomainError("Una regla por producto, categoría o canal indica a cuál")
        return cls(id=new_uuid(), tax_code_id=tax_code_id, scope=scope,
                   scope_id=scope_id if scope != "DEFAULT" else None,
                   effective_from=effective_from, effective_to=effective_to)

    def applies_on(self, on_date: date) -> bool:
        return self.active and self.effective_from <= on_date and (
            self.effective_to is None or on_date <= self.effective_to)

    @property
    def specificity(self) -> int:
        return TAX_RULE_SCOPES.index(self.scope)


@dataclass(slots=True)
class TaxPostingProfile:
    """Cuenta contable del impuesto según su dirección (trasladado/acreditable)."""

    id: str
    tax_code_id: str
    account_id: str
    effective_from: date
    created_at: str = field(default_factory=_utcnow)

    @classmethod
    def create(cls, tax_code_id: str, account_id: str, effective_from: date) -> "TaxPostingProfile":
        if not tax_code_id or not account_id:
            raise FinanceDomainError("El perfil del impuesto requiere código y cuenta")
        return cls(id=new_uuid(), tax_code_id=tax_code_id, account_id=account_id,
                   effective_from=effective_from)


@dataclass(frozen=True, slots=True)
class TaxBreakdown:
    base: Money
    tax: Money
    rate_percent: Decimal

    @property
    def total(self) -> Money:
        return self.base.add(self.tax)


class TaxCalculator:
    """Cálculo puro: impuesto sobre una base, o desglose de un importe con impuesto incluido."""

    @staticmethod
    def on_base(base: Money, rate_percent: Decimal) -> TaxBreakdown:
        tax = base.multiply(Decimal(rate_percent) / Decimal("100"))
        return TaxBreakdown(base=base, tax=tax, rate_percent=Decimal(rate_percent))

    @staticmethod
    def from_inclusive(total: Money, rate_percent: Decimal) -> TaxBreakdown:
        rate = Decimal(rate_percent)
        if rate == 0:
            return TaxBreakdown(base=total, tax=Money.zero(total.currency_code),
                                rate_percent=rate)
        base = Money(total.amount / (Decimal("1") + rate / Decimal("100")),
                     total.currency_code, total.decimal_places, total.rounding_mode)
        # El impuesto es el resto: base + impuesto == total, sin centavo perdido.
        return TaxBreakdown(base=base, tax=total.subtract(base), rate_percent=rate)
