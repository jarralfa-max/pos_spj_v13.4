"""Motor de reglas de acumulación (§13): cuántos puntos da una compra.

Puro y determinista: recibe las reglas, el contexto de la compra y cuántas
veces se ha usado cada regla; devuelve los puntos con su desglose por regla y,
para cada regla que no aplicó, el porqué. Sin E/S, sin `eval`: las condiciones
son datos que `_matches` recorre comparando campos conocidos.

Orden de cálculo:

1. **Selección.** Reglas vigentes, del tipo que se evalúa al cobrar, cuyo
   alcance (sucursal, canal, segmento, programa, forma de pago, productos)
   alcanza la compra, cuya condición se cumple y que no agotaron sus límites.
   Se recorren por prioridad (mayor primero): una regla NO acumulable sólo
   aplica si es la primera, y si aplica ninguna otra lo hace.
2. **Base.** Las reglas POINTS_PER_AMOUNT / POINTS_PER_UNIT seleccionadas; si
   no hay ninguna, la base de la Configuración de Fidelidad (1 punto por cada
   N pesos) — exactamente lo que el POS hacía antes de las reglas.
3. **Multiplicadores** sobre la base de lo que alcanzan.
4. **Bonos** fijos.

Todo punto es entero hacia abajo: nunca se regala una fracción.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from decimal import ROUND_DOWN, Decimal
from typing import Iterable, Mapping

from backend.domain.loyalty.entities.loyalty_rule import LoyaltyRule
from backend.domain.loyalty.enums import SALE_EVALUATED_RULE_TYPES, LoyaltyRuleType as T

_ZERO = Decimal("0")
_BASE_TYPES = frozenset({T.POINTS_PER_AMOUNT, T.POINTS_PER_UNIT})
_LINE_SCOPED_MULTIPLIERS = frozenset({T.CATEGORY_MULTIPLIER, T.PRODUCT_MULTIPLIER})


def _floor(value: Decimal) -> int:
    return int(value.to_integral_value(rounding=ROUND_DOWN)) if value > 0 else 0


@dataclass(frozen=True)
class AccrualLine:
    product_id: str
    quantity: Decimal
    amount: Decimal
    #: Categoría del producto y sus ancestros (una regla de categoría alcanza
    #: también a las subcategorías).
    category_ids: frozenset[str] = frozenset()


@dataclass(frozen=True)
class AccrualContext:
    occurred_at: datetime
    #: Lo que acumula: total pagado sin canjes, sin lo pagado a crédito si la
    #: Configuración no deja acumular a crédito.
    eligible_amount: Decimal
    lines: tuple[AccrualLine, ...] = ()
    customer_id: str | None = None
    branch_id: str | None = None
    channel: str = "POS"
    payments: tuple[tuple[str, Decimal], ...] = ()
    segment_ids: frozenset[str] = frozenset()
    program_ids: frozenset[str] = frozenset()
    #: Compras previas del cliente (fechas), para primera compra y frecuencia.
    previous_purchases: tuple[datetime, ...] = ()
    #: Días entre la compra y el cumpleaños del cliente (con signo, el más
    #: cercano), o None si no hay cumpleaños registrado con consentimiento.
    days_to_birthday: int | None = None

    @property
    def lines_total(self) -> Decimal:
        return sum((ln.amount for ln in self.lines), _ZERO)

    @property
    def units(self) -> Decimal:
        return sum((ln.quantity for ln in self.lines), _ZERO)


@dataclass(frozen=True)
class RuleUsage:
    total: int = 0
    customer: int = 0
    customer_today: int = 0
    customer_month: int = 0


@dataclass(frozen=True)
class AppliedRule:
    rule_id: str | None
    code: str
    name: str
    points: int


@dataclass(frozen=True)
class RejectedRule:
    rule_id: str
    code: str
    name: str
    reason: str


@dataclass(frozen=True)
class RuleEvaluation:
    points: int
    applied: tuple[AppliedRule, ...] = ()
    rejected: tuple[RejectedRule, ...] = ()


@dataclass
class _Selection:
    rules: list[LoyaltyRule] = field(default_factory=list)
    rejected: list[RejectedRule] = field(default_factory=list)


class LoyaltyRuleEngine:
    def __init__(self, *, pesos_per_point: Decimal) -> None:
        self._pesos_per_point = Decimal(str(pesos_per_point))

    # ── entrada ───────────────────────────────────────────────────────────
    def evaluate(self, rules: Iterable[LoyaltyRule], context: AccrualContext,
                 usage: Mapping[str, RuleUsage] | None = None) -> RuleEvaluation:
        usage = usage or {}
        seleccion = self._select(list(rules), context, usage)
        aplicadas: list[AppliedRule] = []
        rechazadas = list(seleccion.rejected)

        bases = [r for r in seleccion.rules if r.rule_type in _BASE_TYPES]
        base_por_regla: list[tuple[LoyaltyRule, int]] = []
        if bases:
            for regla in bases:
                base_por_regla.append((regla, self._base_points(regla, context)))
        base_total = sum(p for _, p in base_por_regla)
        # La base de la Configuración cubre lo que ninguna regla base alcanza: una
        # regla base sin alcance la sustituye entera; una con alcance (p. ej.
        # "carnes: 1 punto por cada $5") sólo para sus productos.
        defecto = self._default_base(context, bases)
        if defecto:
            aplicadas.append(AppliedRule(None, "BASE", "Acumulación base (Configuración)",
                                         defecto))
            base_total += defecto
        for regla, puntos in base_por_regla:
            self._record(regla, puntos, aplicadas, rechazadas)

        for regla in seleccion.rules:
            if regla.rule_type in _BASE_TYPES:
                continue
            self._record(regla, self._extra_points(regla, context, base_total),
                         aplicadas, rechazadas)
        return RuleEvaluation(points=sum(a.points for a in aplicadas),
                              applied=tuple(aplicadas), rejected=tuple(rechazadas))

    @staticmethod
    def _record(regla: LoyaltyRule, puntos: int, aplicadas: list, rechazadas: list) -> None:
        if puntos > 0:
            aplicadas.append(AppliedRule(regla.id, regla.code, regla.name, puntos))
        else:
            rechazadas.append(RejectedRule(regla.id, regla.code, regla.name,
                                           "La compra no alcanza a generar puntos con esta regla"))

    # ── selección ─────────────────────────────────────────────────────────
    def _select(self, rules: list[LoyaltyRule], ctx: AccrualContext,
                usage: Mapping[str, RuleUsage]) -> _Selection:
        sel = _Selection()
        momento = ctx.occurred_at.isoformat(timespec="seconds")
        exclusiva = False
        for regla in sorted(rules, key=lambda r: (-r.priority, r.code)):
            motivo = self._why_not(regla, ctx, momento, usage.get(regla.id, RuleUsage()))
            if motivo is None and exclusiva:
                motivo = "Otra regla de mayor prioridad no es acumulable"
            if motivo is None and not regla.stackable and sel.rules:
                motivo = "No es acumulable y ya aplicó una regla de mayor prioridad"
            if motivo is not None:
                sel.rejected.append(RejectedRule(regla.id, regla.code, regla.name, motivo))
                continue
            sel.rules.append(regla)
            exclusiva = exclusiva or not regla.stackable
        return sel

    def _why_not(self, regla: LoyaltyRule, ctx: AccrualContext, momento: str,
                 uso: RuleUsage) -> str | None:
        if regla.rule_type not in SALE_EVALUATED_RULE_TYPES:
            return "Este tipo de regla no se evalúa al cobrar"
        if not regla.is_in_effect(momento):
            return "Fuera de vigencia o inactiva"
        if regla.program_id and regla.program_id not in ctx.program_ids:
            return "El cliente no pertenece al programa de la regla"
        if regla.branch_scope and (ctx.branch_id or "") not in regla.branch_scope:
            return "Sucursal fuera del alcance"
        if regla.channel_scope and ctx.channel not in regla.channel_scope:
            return "Canal fuera del alcance"
        if regla.customer_segment_scope and not (ctx.segment_ids & set(regla.customer_segment_scope)):
            return "El cliente no está en los segmentos de la regla"
        if regla.payment_method_scope and not self._paid_in_scope(regla, ctx):
            return "Ninguna forma de pago está en el alcance"
        if (regla.product_scope or regla.category_scope) and not self._scoped_lines(regla, ctx):
            return "Ningún producto de la venta está en el alcance"
        if not _matches(regla.condition_definition, _facts(ctx)):
            return "No se cumple la condición"
        if regla.rule_type is T.FIRST_PURCHASE_BONUS and ctx.previous_purchases:
            return "No es la primera compra del cliente"
        if regla.rule_type is T.VISIT_FREQUENCY_BONUS and not self._frequent(regla, ctx):
            return "Aún no alcanza las visitas requeridas"
        if regla.rule_type is T.BIRTHDAY_BONUS:
            if ctx.days_to_birthday is None:
                return "El cliente no tiene cumpleaños registrado (con consentimiento)"
            if abs(ctx.days_to_birthday) > int(regla.benefit_definition.get("window_days") or 0):
                return "No es la fecha de cumpleaños del cliente"
        if regla.maximum_uses is not None and uso.total >= regla.maximum_uses:
            return "Agotó sus usos totales"
        if regla.customer_limit is not None and ctx.customer_id and uso.customer >= regla.customer_limit:
            return "El cliente agotó sus usos de esta regla"
        if regla.daily_limit is not None and ctx.customer_id and uso.customer_today >= regla.daily_limit:
            return "El cliente ya usó esta regla hoy"
        if regla.monthly_limit is not None and ctx.customer_id and uso.customer_month >= regla.monthly_limit:
            return "El cliente ya usó esta regla este mes"
        return None

    # ── cálculo ───────────────────────────────────────────────────────────
    @staticmethod
    def _scoped_lines(regla: LoyaltyRule, ctx: AccrualContext) -> list[AccrualLine]:
        if not (regla.product_scope or regla.category_scope):
            return list(ctx.lines)
        productos, categorias = set(regla.product_scope), set(regla.category_scope)
        return [ln for ln in ctx.lines
                if ln.product_id in productos or (ln.category_ids & categorias)]

    def _eligible_share(self, regla: LoyaltyRule, ctx: AccrualContext) -> Decimal:
        """Parte del importe que acumula atribuible a las líneas del alcance (el
        descuento y el crédito se reparten en proporción)."""
        total = ctx.lines_total
        if not (regla.product_scope or regla.category_scope) or total <= 0:
            return ctx.eligible_amount
        alcance = sum((ln.amount for ln in self._scoped_lines(regla, ctx)), _ZERO)
        return ctx.eligible_amount * alcance / total

    def _default_base(self, ctx: AccrualContext, bases: list[LoyaltyRule]) -> int:
        if self._pesos_per_point <= 0:
            return 0
        if any(not (r.product_scope or r.category_scope) for r in bases):
            return 0
        importe = ctx.eligible_amount
        if bases and ctx.lines_total > 0:
            cubiertas = {id(ln) for r in bases for ln in self._scoped_lines(r, ctx)}
            libre = sum((ln.amount for ln in ctx.lines if id(ln) not in cubiertas), _ZERO)
            importe = ctx.eligible_amount * libre / ctx.lines_total
        return _floor(importe / self._pesos_per_point)

    def _base_points(self, regla: LoyaltyRule, ctx: AccrualContext) -> int:
        b = regla.benefit_definition
        if regla.rule_type is T.POINTS_PER_AMOUNT:
            return _floor(self._eligible_share(regla, ctx) / Decimal(b["amount"])) * \
                int(Decimal(b["points"]))
        unidades = sum((ln.quantity for ln in self._scoped_lines(regla, ctx)), _ZERO)
        return _floor(unidades * Decimal(b["points"]))

    def _extra_points(self, regla: LoyaltyRule, ctx: AccrualContext, base: int) -> int:
        b = regla.benefit_definition
        t = regla.rule_type
        if "multiplier" in b:
            extra = Decimal(b["multiplier"]) - 1
            if t in _LINE_SCOPED_MULTIPLIERS or (t is T.CAMPAIGN_BONUS
                                                  and (regla.product_scope or regla.category_scope)):
                proporcion = (self._eligible_share(regla, ctx) / ctx.eligible_amount
                              if ctx.eligible_amount > 0 else _ZERO)
                return _floor(Decimal(base) * proporcion * extra)
            if t is T.PAYMENT_METHOD_MULTIPLIER:
                pagado = sum((a for _, a in ctx.payments), _ZERO)
                proporcion = (self._paid_in_scope(regla, ctx) / pagado) if pagado > 0 else _ZERO
                return _floor(Decimal(base) * min(proporcion, Decimal("1")) * extra)
            return _floor(Decimal(base) * extra)
        return int(Decimal(b["points"]))

    @staticmethod
    def _paid_in_scope(regla: LoyaltyRule, ctx: AccrualContext) -> Decimal:
        metodos = set(regla.payment_method_scope)
        return sum((a for m, a in ctx.payments if m in metodos), _ZERO)

    @staticmethod
    def _frequent(regla: LoyaltyRule, ctx: AccrualContext) -> bool:
        b = regla.benefit_definition
        desde = ctx.occurred_at - timedelta(days=int(Decimal(b["days"])))
        visitas = 1 + sum(1 for f in ctx.previous_purchases if f >= desde)
        return visitas >= int(Decimal(b["visits"]))


#: Tipos cuyo resultado es un bono FIJO (no proporcional a lo comprado).
FIXED_BONUS_TYPES = frozenset({T.FIXED_BONUS, T.FIRST_PURCHASE_BONUS, T.VISIT_FREQUENCY_BONUS,
                               T.CAMPAIGN_BONUS, T.BIRTHDAY_BONUS})


def is_fixed_bonus(rule: LoyaltyRule) -> bool:
    return rule.rule_type in FIXED_BONUS_TYPES and "points" in rule.benefit_definition


def condition_holds_for_subtotal(condition: dict, subtotal: Decimal) -> bool:
    """¿La condición se sigue cumpliendo con otro importe (lo que queda tras una
    devolución)? Sólo cambia el importe: día, hora y compras previas son los de
    la compra original, que ya la cumplía; las comparaciones que no son de
    importe se toman por cumplidas."""
    def evaluar(c: dict) -> bool:
        if not c:
            return True
        if "all" in c:
            return all(evaluar(x) for x in c["all"])
        if "any" in c:
            return any(evaluar(x) for x in c["any"])
        if "not" in c:
            interno = c["not"]
            return True if "field" in interno and interno["field"] != "subtotal"                 else not evaluar(interno)
        if c.get("field") != "subtotal":
            return True
        return _matches(c, {"subtotal": Decimal(subtotal)})
    return evaluar(condition)


# ── condiciones declarativas ──────────────────────────────────────────────
def _facts(ctx: AccrualContext) -> dict[str, Decimal]:
    return {
        "subtotal": ctx.eligible_amount,
        "units": ctx.units,
        "line_count": Decimal(len(ctx.lines)),
        "weekday": Decimal(ctx.occurred_at.weekday()),
        "hour": Decimal(ctx.occurred_at.hour),
        "day_of_month": Decimal(ctx.occurred_at.day),
        "purchase_count": Decimal(len(ctx.previous_purchases)),
    }


def _matches(condition: dict, facts: Mapping[str, Decimal]) -> bool:
    if not condition:
        return True
    if "all" in condition:
        return all(_matches(c, facts) for c in condition["all"])
    if "any" in condition:
        return any(_matches(c, facts) for c in condition["any"])
    if "not" in condition:
        return not _matches(condition["not"], facts)
    valor = facts[condition["field"]]
    op = condition["op"]
    objetivo = condition["value"]
    if op in ("in", "not_in"):
        dentro = valor in {Decimal(str(v)) for v in objetivo}
        return dentro if op == "in" else not dentro
    if op == "between":
        bajo, alto = (Decimal(str(v)) for v in objetivo)
        return bajo <= valor <= alto
    o = Decimal(str(objetivo))
    return {"eq": valor == o, "ne": valor != o, "gt": valor > o, "gte": valor >= o,
            "lt": valor < o, "lte": valor <= o}[op]


__all__ = ["AccrualContext", "AccrualLine", "AppliedRule", "LoyaltyRuleEngine",
           "RejectedRule", "RuleEvaluation", "RuleUsage"]
