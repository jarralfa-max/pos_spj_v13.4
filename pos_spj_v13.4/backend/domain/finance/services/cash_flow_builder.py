"""Estado de flujo de efectivo — MÉTODO DIRECTO (auditoría d9f2bca F04).

El cálculo anterior sumaba saldos naturales por categoría de cuenta: una
aportación bancaria de 100 aparecía como 100 de operación (el banco es una
cuenta OPERATING) y 100 de financiamiento (el capital), variación neta 200; una
venta a crédito aparecía como 100 de efectivo sin un peso cobrado.

Aquí el flujo se mide sobre el EFECTIVO real: por cada asiento, la variación de
sus líneas en cuentas de efectivo y equivalentes; esa variación se clasifica por
la categoría de las contrapartidas del lado opuesto (proporcionalmente si hay
varias). Consecuencias, por construcción:
- un asiento sin líneas de efectivo (venta a crédito, depreciación) no es flujo;
- una transferencia entre cuentas de efectivo neta cero y no aparece;
- la variación neta es exactamente efectivo final − efectivo inicial.

Puro: sin SQL. La capa de consulta decide qué cuentas son efectivo.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal

from backend.domain.finance.enums import CashFlowCategory
from backend.domain.finance.exceptions import FinanceDomainError
from backend.domain.finance.value_objects.money import Money

_SECTIONS = (CashFlowCategory.OPERATING, CashFlowCategory.INVESTING,
             CashFlowCategory.FINANCING)


@dataclass(frozen=True, slots=True)
class CashFlowLine:
    account_id: str
    is_cash: bool
    category: CashFlowCategory
    debit: Decimal
    credit: Decimal


@dataclass(slots=True)
class CashFlowEntry:
    entry_id: str
    lines: list[CashFlowLine] = field(default_factory=list)


def _section(category: CashFlowCategory) -> CashFlowCategory:
    # Ingresos, gastos y cuentas sin categoría explícita son operación.
    return category if category in _SECTIONS else CashFlowCategory.OPERATING


class CashFlowBuilder:
    def __init__(self, currency_code: str = "MXN") -> None:
        self._currency = currency_code

    def build(self, entries: list[CashFlowEntry], *, opening_cash: Decimal,
              closing_cash: Decimal) -> dict:
        flows = {section: Decimal("0") for section in _SECTIONS}
        for entry in entries:
            cash_delta = sum((l.debit - l.credit for l in entry.lines if l.is_cash),
                             Decimal("0"))
            if cash_delta == 0:
                continue
            # Contrapartidas del lado opuesto al efectivo: si entra efectivo
            # (débito), las que se acreditan; si sale, las que se debitan.
            if cash_delta > 0:
                weights = [(l, l.credit - l.debit) for l in entry.lines
                           if not l.is_cash and l.credit > l.debit]
            else:
                weights = [(l, l.debit - l.credit) for l in entry.lines
                           if not l.is_cash and l.debit > l.credit]
            total_weight = sum((w for _, w in weights), Decimal("0"))
            if total_weight == 0:
                flows[CashFlowCategory.OPERATING] += cash_delta
                continue
            allocated = Decimal("0")
            for index, (line, weight) in enumerate(weights):
                if index == len(weights) - 1:
                    share = cash_delta - allocated
                else:
                    share = (cash_delta * weight / total_weight).quantize(Decimal("0.01"))
                    allocated += share
                flows[_section(line.category)] += share
        net = sum(flows.values(), Decimal("0"))
        if net != closing_cash - opening_cash:
            raise FinanceDomainError(
                f"El flujo neto {net} no reconcilia con la variación de efectivo "
                f"{closing_cash - opening_cash}")
        money = lambda value: Money(value, self._currency).to_string()  # noqa: E731
        return {
            "operating": money(flows[CashFlowCategory.OPERATING]),
            "investing": money(flows[CashFlowCategory.INVESTING]),
            "financing": money(flows[CashFlowCategory.FINANCING]),
            "net_change_in_cash": money(net),
            "opening_cash": money(opening_cash),
            "closing_cash": money(closing_cash),
            "method": "DIRECT",
        }
