"""FinanceSettings — parámetros configurables del contexto financiero.

Todo umbral funcional vive aquí, nunca en código de pantalla ni en handlers
(SPJ_REFACTOR_SKILL §1.24). Los valores por omisión son conservadores: cero o
vacío para importes y tolerancias, segregación de funciones activa.
"""

from __future__ import annotations

from dataclasses import dataclass, fields, replace
from decimal import Decimal, InvalidOperation

from backend.domain.finance.exceptions import FinanceDomainError


@dataclass(frozen=True, slots=True)
class FinanceSettings:
    #: Moneda base de la empresa (§24).
    base_currency_code: str = "MXN"
    #: Cuenta de diferencias de redondeo por conversión (§24).
    rounding_account_id: str | None = None
    #: §28: quien crea un asiento manual no lo contabiliza.
    journal_review_required: bool = True
    #: §28: quien autoriza un pago no lo ejecuta.
    payment_dual_control: bool = True
    #: §28: importe desde el cual un pago exige segunda autorización (vacío = nunca).
    payment_second_authorization_threshold: Decimal | None = None
    #: §28: quien importa un estado bancario no aprueba sus propios ajustes.
    statement_importer_cannot_adjust: bool = True
    #: §16: porcentaje consumido desde el cual una partida queda en ADVERTENCIA (vacío = sin advertencia).
    budget_warning_percent: Decimal | None = None
    #: §15: tolerancia de importe y ventana de días para sugerir conciliaciones.
    reconciliation_amount_tolerance: Decimal = Decimal("0")
    reconciliation_date_window_days: int = 0
    #: §16 cierre: diferencia auxiliar contra mayor que se considera material.
    close_materiality_threshold: Decimal = Decimal("0.01")
    #: §11: importe desde el cual castigar una CxC exige autorización explícita
    #: (vacío = todo castigo exige el permiso de castigo, que siempre se exige).
    receivable_write_off_threshold: Decimal | None = None
    #: §32/§29: horizontes de planeación y alertas (configuración, no pantalla).
    cash_projection_weeks: int = 13
    payroll_history_months: int = 3
    upcoming_payments_days: int = 7
    dashboard_trend_months: int = 6

    def with_changes(self, **changes) -> "FinanceSettings":
        unknown = set(changes) - {f.name for f in fields(self)}
        if unknown:
            raise FinanceDomainError(f"Parámetros desconocidos: {sorted(unknown)}")
        coerced = {name: _coerce(name, value) for name, value in changes.items()}
        result = replace(self, **coerced)
        result.validate()
        return result

    def validate(self) -> None:
        code = (self.base_currency_code or "").upper()
        if len(code) != 3 or not code.isalpha():
            raise FinanceDomainError("Moneda base inválida")
        for name in ("payment_second_authorization_threshold", "budget_warning_percent",
                     "receivable_write_off_threshold"):
            value = getattr(self, name)
            if value is not None and value < 0:
                raise FinanceDomainError(f"{name} no puede ser negativo")
        if self.budget_warning_percent is not None and self.budget_warning_percent > 100:
            raise FinanceDomainError("El porcentaje de advertencia va de 0 a 100")
        if self.reconciliation_amount_tolerance < 0 or self.reconciliation_date_window_days < 0:
            raise FinanceDomainError("La tolerancia de conciliación no puede ser negativa")
        for name in ("cash_projection_weeks", "payroll_history_months",
                     "upcoming_payments_days", "dashboard_trend_months"):
            if getattr(self, name) < 0:
                raise FinanceDomainError(f"{name} no puede ser negativo")
        if self.close_materiality_threshold < 0:
            raise FinanceDomainError("El umbral de materialidad no puede ser negativo")

    def as_storage(self) -> dict[str, str]:
        result: dict[str, str] = {}
        for f in fields(self):
            value = getattr(self, f.name)
            if value is None:
                result[f.name] = ""
            elif isinstance(value, bool):
                result[f.name] = "1" if value else "0"
            else:
                result[f.name] = str(value)
        return result

    @classmethod
    def from_storage(cls, raw: dict[str, str]) -> "FinanceSettings":
        base = cls()
        known = {f.name for f in fields(cls)}
        return base.with_changes(**{k: v for k, v in raw.items() if k in known})


_BOOL = {"journal_review_required", "payment_dual_control", "statement_importer_cannot_adjust"}
_OPTIONAL_DECIMAL = {"payment_second_authorization_threshold", "budget_warning_percent",
                     "receivable_write_off_threshold"}
_DECIMAL = {"reconciliation_amount_tolerance", "close_materiality_threshold"}
_INT = {"reconciliation_date_window_days", "cash_projection_weeks", "payroll_history_months",
        "upcoming_payments_days", "dashboard_trend_months"}
_OPTIONAL_TEXT = {"rounding_account_id"}


def _coerce(name: str, value):
    if isinstance(value, float):
        raise FinanceDomainError(f"{name}: no se aceptan valores float")
    if name in _BOOL:
        if isinstance(value, str):
            return value.strip().lower() in ("1", "true", "si", "sí", "yes")
        return bool(value)
    if name in _OPTIONAL_DECIMAL or name in _DECIMAL:
        text = "" if value is None else str(value).strip()
        if not text:
            if name in _OPTIONAL_DECIMAL:
                return None
            return Decimal("0")
        try:
            return Decimal(text)
        except InvalidOperation as exc:
            raise FinanceDomainError(f"{name}: importe inválido {text!r}") from exc
    if name in _INT:
        text = str(value).strip() if value is not None else "0"
        if not text.lstrip("-").isdigit():
            raise FinanceDomainError(f"{name}: entero inválido {text!r}")
        return int(text or "0")
    if name in _OPTIONAL_TEXT:
        text = "" if value is None else str(value).strip()
        return text or None
    return str(value).strip().upper() if name == "base_currency_code" else value
