"""StackingPolicy (§24): qué beneficios se combinan en una misma venta.

Las combinaciones posibles son las de `StackingCombination`; lo que pasa con
cada una es CONFIGURACIÓN (`loyalty_stacking_rules`), nunca un `if` en código.
Una combinación sin configurar se permite.

Opciones, para un beneficio nuevo frente a uno ya aceptado:

* ``ALLOW`` — ambos.
* ``DENY`` — no se combinan: el que llegó después queda fuera.
* ``EXCLUSIVE`` — no se combinan y SIEMPRE gana el primer tipo del nombre de
  la combinación (``COUPON_VOUCHER`` exclusivo: gana el cupón aunque el vale
  se haya pedido antes).
* ``ALLOW_WITH_LIMIT`` — ambos, pero juntos no pasan de ``limit_value`` pesos:
  el nuevo se recorta.
* ``BEST_BENEFIT_ONLY`` — sólo el de mayor valor.
* ``PRIORITY_ORDER`` — sólo el de tipo con mayor prioridad en
  ``priority_order``; mismo tipo: el primero.

Pura: sin E/S, sólo Decimal.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from decimal import Decimal
from typing import Iterable, Mapping

from backend.domain.loyalty.enums import StackingCombination, StackingOption

#: Tipos de beneficio que participan en la política.
BENEFIT_KINDS = ("POINTS", "COUPON", "VOUCHER", "PROMOTION", "EMPLOYEE_DISCOUNT",
                 "GIFT_CARD", "STORE_CREDIT")

_PAIRS: dict[frozenset, StackingCombination] = {
    frozenset({"POINTS", "COUPON"}): StackingCombination.POINTS_COUPON,
    frozenset({"POINTS", "VOUCHER"}): StackingCombination.POINTS_VOUCHER,
    frozenset({"COUPON", "VOUCHER"}): StackingCombination.COUPON_VOUCHER,
    frozenset({"COUPON"}): StackingCombination.COUPON_COUPON,
    frozenset({"PROMOTION", "COUPON"}): StackingCombination.PROMOTION_COUPON,
    frozenset({"EMPLOYEE_DISCOUNT", "COUPON"}): StackingCombination.EMPLOYEE_DISCOUNT_COUPON,
    frozenset({"GIFT_CARD", "POINTS"}): StackingCombination.GIFT_CARD_POINTS,
    frozenset({"STORE_CREDIT", "COUPON"}): StackingCombination.STORE_CREDIT_COUPON,
}


def combination_for(kind_a: str, kind_b: str) -> StackingCombination | None:
    return _PAIRS.get(frozenset({kind_a, kind_b}))


def _leading_kind(combination: StackingCombination) -> str:
    """Primer tipo del nombre (POINTS_COUPON → POINTS; EMPLOYEE_DISCOUNT_COUPON
    → EMPLOYEE_DISCOUNT)."""
    nombre = combination.value
    for kind in sorted(BENEFIT_KINDS, key=len, reverse=True):
        if nombre.startswith(kind + "_"):
            return kind
    return nombre.split("_", 1)[0]


@dataclass(frozen=True)
class StackingSetting:
    combination: StackingCombination
    option: StackingOption = StackingOption.ALLOW
    limit_value: Decimal | None = None
    priority_order: tuple[str, ...] = ()


@dataclass(frozen=True)
class Benefit:
    kind: str
    reference: str
    value: Decimal
    label: str = ""


@dataclass(frozen=True)
class StackingResult:
    accepted: tuple[Benefit, ...]
    rejected: tuple[tuple[Benefit, str], ...] = ()
    #: Beneficios recortados por ALLOW_WITH_LIMIT: (beneficio aceptado, valor pedido).
    capped: tuple[tuple[Benefit, Decimal], ...] = field(default_factory=tuple)


class StackingPolicy:
    def __init__(self, settings: Iterable[StackingSetting] = ()) -> None:
        self._settings: Mapping[StackingCombination, StackingSetting] = {
            s.combination: s for s in settings}

    def setting(self, combination: StackingCombination) -> StackingSetting:
        return self._settings.get(combination, StackingSetting(combination))

    def resolve(self, requested: Iterable[Benefit]) -> StackingResult:
        aceptados: list[Benefit] = []
        rechazados: list[tuple[Benefit, str]] = []
        recortados: list[tuple[Benefit, Decimal]] = []
        for nuevo in requested:
            vigente: Benefit | None = nuevo
            for previo in list(aceptados):
                if vigente is None:
                    break
                combinacion = combination_for(previo.kind, vigente.kind)
                if combinacion is None:
                    continue
                ajuste = self.setting(combinacion)
                opcion = ajuste.option
                nombre = _LABELS.get(combinacion, combinacion.value)
                if opcion is StackingOption.ALLOW:
                    continue
                if opcion is StackingOption.DENY:
                    rechazados.append((vigente, f"No se combina con {previo.label or previo.kind} ({nombre})"))
                    vigente = None
                elif opcion is StackingOption.EXCLUSIVE:
                    gana = _leading_kind(combinacion)
                    if vigente.kind == gana and previo.kind != gana:
                        aceptados.remove(previo)
                        rechazados.append((previo, f"{nombre}: es exclusivo y prevalece {gana}"))
                    else:
                        rechazados.append((vigente, f"{nombre}: es exclusivo y prevalece {gana}"))
                        vigente = None
                elif opcion is StackingOption.ALLOW_WITH_LIMIT:
                    tope = ajuste.limit_value if ajuste.limit_value is not None else Decimal("0")
                    disponible = tope - previo.value
                    if disponible <= 0:
                        rechazados.append((vigente, f"{nombre}: se alcanzó el tope de ${tope}"))
                        vigente = None
                    elif vigente.value > disponible:
                        recortados.append((replace(vigente, value=disponible), vigente.value))
                        vigente = replace(vigente, value=disponible)
                elif opcion is StackingOption.BEST_BENEFIT_ONLY:
                    if vigente.value > previo.value:
                        aceptados.remove(previo)
                        rechazados.append((previo, f"{nombre}: sólo aplica el beneficio mayor"))
                    else:
                        rechazados.append((vigente, f"{nombre}: sólo aplica el beneficio mayor"))
                        vigente = None
                elif opcion is StackingOption.PRIORITY_ORDER:
                    orden = list(ajuste.priority_order)
                    rango = {k: i for i, k in enumerate(orden)}
                    if rango.get(vigente.kind, len(orden)) < rango.get(previo.kind, len(orden)):
                        aceptados.remove(previo)
                        rechazados.append((previo, f"{nombre}: prevalece {vigente.kind} por prioridad"))
                    else:
                        rechazados.append((vigente, f"{nombre}: prevalece {previo.kind} por prioridad"))
                        vigente = None
            if vigente is not None:
                aceptados.append(vigente)
        return StackingResult(tuple(aceptados), tuple(rechazados), tuple(recortados))


_LABELS = {
    StackingCombination.POINTS_COUPON: "puntos + cupón",
    StackingCombination.POINTS_VOUCHER: "puntos + vale",
    StackingCombination.COUPON_VOUCHER: "cupón + vale",
    StackingCombination.COUPON_COUPON: "varios cupones",
    StackingCombination.PROMOTION_COUPON: "promoción + cupón",
    StackingCombination.EMPLOYEE_DISCOUNT_COUPON: "descuento de empleado + cupón",
    StackingCombination.GIFT_CARD_POINTS: "tarjeta de regalo + puntos",
    StackingCombination.STORE_CREDIT_COUPON: "saldo a favor + cupón",
}


__all__ = ["BENEFIT_KINDS", "Benefit", "StackingPolicy", "StackingResult", "StackingSetting",
           "combination_for"]
