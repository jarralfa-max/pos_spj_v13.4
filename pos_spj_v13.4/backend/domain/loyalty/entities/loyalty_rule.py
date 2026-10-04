"""LoyaltyRule — regla declarativa de acumulación (§13, 2026-10-03).

Decisión del usuario: "las reglas salen de Fidelidad y el POS las ejecuta".
Una regla es DATOS, nunca código: tipo, prioridad, condición y beneficio en un
esquema declarativo cerrado que este módulo valida al crearla. No hay `eval`
ni `exec` en ningún punto; el motor (`services/rule_engine.py`) sólo sabe
comparar campos conocidos con operadores conocidos.

Ciclo: DRAFT → ACTIVE (la activa OTRA persona, §60) → INACTIVE → ACTIVE...
Una regla activa no se edita: se desactiva, se corrige y se vuelve a activar.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Any

from backend.domain.loyalty.enums import (
    SALE_EVALUATED_RULE_TYPES,
    LoyaltyRuleStatus,
    LoyaltyRuleType,
)
from backend.domain.loyalty.exceptions import (
    InvalidLoyaltyRuleError,
    InvalidLoyaltyRuleStateError,
    LoyaltySegregationOfDutiesError,
)
from backend.shared.ids import new_uuid

#: Campos que una condición puede consultar, con su tipo.
CONDITION_FIELDS: dict[str, str] = {
    "subtotal": "decimal",        # importe que acumula (pagado, sin canjes)
    "units": "decimal",           # unidades vendidas
    "line_count": "int",          # renglones de la venta
    "weekday": "int",             # 0 = lunes … 6 = domingo
    "hour": "int",                # 0-23, hora local de la venta
    "day_of_month": "int",
    "purchase_count": "int",      # compras previas del cliente
}
CONDITION_OPERATORS = frozenset({"eq", "ne", "gt", "gte", "lt", "lte", "in", "not_in", "between"})
_MAX_DEPTH = 5
_MAX_LEAVES = 20

CHANNELS = ("POS", "WHATSAPP", "DELIVERY", "ECOMMERCE")
PAYMENT_METHODS = ("CASH", "CARD", "TRANSFER", "MERCADO_PAGO", "CREDIT")

_MULTIPLIERS = frozenset({
    LoyaltyRuleType.CATEGORY_MULTIPLIER, LoyaltyRuleType.PRODUCT_MULTIPLIER,
    LoyaltyRuleType.BRANCH_MULTIPLIER, LoyaltyRuleType.CHANNEL_MULTIPLIER,
    LoyaltyRuleType.PAYMENT_METHOD_MULTIPLIER,
})
#: Alcance que cada multiplicador NECESITA (sin él multiplicaría todo).
_REQUIRED_SCOPE = {
    LoyaltyRuleType.CATEGORY_MULTIPLIER: "category_scope",
    LoyaltyRuleType.PRODUCT_MULTIPLIER: "product_scope",
    LoyaltyRuleType.BRANCH_MULTIPLIER: "branch_scope",
    LoyaltyRuleType.CHANNEL_MULTIPLIER: "channel_scope",
    LoyaltyRuleType.PAYMENT_METHOD_MULTIPLIER: "payment_method_scope",
}
#: Dónde vive cada tipo que NO se evalúa al cobrar.
_OWN_FLOW = {
    LoyaltyRuleType.BIRTHDAY_BONUS: "Beneficios → Cumpleaños",
    LoyaltyRuleType.REFERRAL_BONUS: "Beneficios → Referidos",
    LoyaltyRuleType.CHALLENGE_REWARD: "Beneficios → Retos y misiones",
}
_MAX_MULTIPLIER = Decimal("10")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _positive(value: Any, label: str, *, integer: bool = False) -> Decimal:
    if isinstance(value, float):
        raise InvalidLoyaltyRuleError(f"{label}: usa texto decimal, nunca float")
    try:
        numero = Decimal(str(value))
    except (InvalidOperation, ValueError):
        raise InvalidLoyaltyRuleError(f"{label}: «{value}» no es un número") from None
    if not numero.is_finite() or numero <= 0:
        raise InvalidLoyaltyRuleError(f"{label} debe ser mayor a cero")
    if integer and numero != numero.to_integral_value():
        raise InvalidLoyaltyRuleError(f"{label} debe ser un número entero")
    return numero


def validate_condition(condition: Any, *, depth: int = 0) -> int:
    """Valida una condición declarativa; devuelve cuántas hojas tiene.

    Forma: ``{}`` (siempre), ``{"all": [...]}``, ``{"any": [...]}``,
    ``{"not": {...}}`` o una hoja ``{"field", "op", "value"}``."""
    if depth > _MAX_DEPTH:
        raise InvalidLoyaltyRuleError("La condición anida demasiados niveles")
    if not isinstance(condition, dict):
        raise InvalidLoyaltyRuleError("Cada condición debe ser un objeto")
    if not condition:
        return 0
    llaves = set(condition)
    if llaves in ({"all"}, {"any"}):
        hijos = condition[next(iter(llaves))]
        if not isinstance(hijos, list) or not hijos:
            raise InvalidLoyaltyRuleError("«all»/«any» necesitan una lista con condiciones")
        hojas = sum(validate_condition(h, depth=depth + 1) for h in hijos)
    elif llaves == {"not"}:
        hojas = validate_condition(condition["not"], depth=depth + 1)
    elif llaves == {"field", "op", "value"}:
        campo, op, valor = condition["field"], condition["op"], condition["value"]
        if campo not in CONDITION_FIELDS:
            raise InvalidLoyaltyRuleError(
                f"Campo «{campo}» no permitido; usa: {', '.join(CONDITION_FIELDS)}")
        if op not in CONDITION_OPERATORS:
            raise InvalidLoyaltyRuleError(f"Operador «{op}» no permitido")
        valores = valor if op in ("in", "not_in", "between") else [valor]
        if not isinstance(valores, list) or not valores:
            raise InvalidLoyaltyRuleError(f"«{op}» necesita una lista de valores")
        if op == "between" and len(valores) != 2:
            raise InvalidLoyaltyRuleError("«between» necesita exactamente dos valores")
        for v in valores:
            if isinstance(v, (float, bool)) or not isinstance(v, (int, str)):
                raise InvalidLoyaltyRuleError("Los valores de una condición son texto o enteros")
            try:
                Decimal(str(v))
            except InvalidOperation:
                raise InvalidLoyaltyRuleError(f"«{v}» no es un número") from None
        hojas = 1
    else:
        raise InvalidLoyaltyRuleError(f"Condición con llaves no permitidas: {sorted(llaves)}")
    if hojas > _MAX_LEAVES:
        raise InvalidLoyaltyRuleError("La condición tiene demasiadas comparaciones")
    return hojas


def validate_benefit(rule_type: LoyaltyRuleType, benefit: Any) -> dict:
    if not isinstance(benefit, dict):
        raise InvalidLoyaltyRuleError("El beneficio debe ser un objeto")
    t = rule_type
    if t is LoyaltyRuleType.POINTS_PER_AMOUNT:
        esperado = {"amount", "points"}
    elif t in _MULTIPLIERS:
        esperado = {"multiplier"}
    elif t is LoyaltyRuleType.VISIT_FREQUENCY_BONUS:
        esperado = {"points", "visits", "days"}
    elif t is LoyaltyRuleType.CAMPAIGN_BONUS:
        esperado = {"points"} if "points" in benefit else {"multiplier"}
    else:
        esperado = {"points"}
    if set(benefit) != esperado:
        raise InvalidLoyaltyRuleError(
            f"El beneficio de {t.value} lleva exactamente: {', '.join(sorted(esperado))}")
    limpio: dict[str, str] = {}
    for llave in esperado:
        entero = llave in ("visits", "days")
        numero = _positive(benefit[llave], llave, integer=entero)
        limpio[llave] = str(numero)
    if "multiplier" in limpio:
        m = Decimal(limpio["multiplier"])
        if m <= 1 or m > _MAX_MULTIPLIER:
            raise InvalidLoyaltyRuleError("El multiplicador va de más de 1 hasta 10")
    if t is LoyaltyRuleType.VISIT_FREQUENCY_BONUS and Decimal(limpio["visits"]) < 2:
        raise InvalidLoyaltyRuleError("La frecuencia de visitas necesita al menos 2 visitas")
    return limpio


def _scope(values: Any, label: str, allowed: tuple[str, ...] | None = None) -> tuple[str, ...]:
    if values in (None, ""):
        return ()
    if isinstance(values, str):
        values = [v.strip() for v in values.replace("\n", ",").split(",")]
    limpio = tuple(dict.fromkeys(str(v).strip() for v in values if str(v).strip()))
    if allowed is not None:
        fuera = [v for v in limpio if v not in allowed]
        if fuera:
            raise InvalidLoyaltyRuleError(
                f"{label}: {', '.join(fuera)} no es válido; usa {', '.join(allowed)}")
    return limpio


def _limit(value: Any, label: str) -> int | None:
    if value in (None, "", 0, "0"):
        return None
    return int(_positive(value, label, integer=True))


@dataclass
class LoyaltyRule:
    id: str
    code: str
    name: str
    rule_type: LoyaltyRuleType
    created_by_user_id: str
    priority: int = 100
    program_id: str | None = None
    condition_definition: dict = field(default_factory=dict)
    benefit_definition: dict = field(default_factory=dict)
    effective_from: str | None = None
    effective_to: str | None = None
    stackable: bool = True
    maximum_uses: int | None = None
    customer_limit: int | None = None
    daily_limit: int | None = None
    monthly_limit: int | None = None
    branch_scope: tuple[str, ...] = ()
    channel_scope: tuple[str, ...] = ()
    payment_method_scope: tuple[str, ...] = ()
    product_scope: tuple[str, ...] = ()
    category_scope: tuple[str, ...] = ()
    customer_segment_scope: tuple[str, ...] = ()
    status: LoyaltyRuleStatus = LoyaltyRuleStatus.DRAFT
    activated_by_user_id: str | None = None
    activated_at: str | None = None
    deactivated_at: str | None = None
    created_at: str = field(default_factory=_now)
    updated_at: str = field(default_factory=_now)

    # ── creación y edición ────────────────────────────────────────────────
    @classmethod
    def create(cls, *, code: str, name: str, rule_type: LoyaltyRuleType | str,
               created_by_user_id: str, **definition) -> "LoyaltyRule":
        rule = cls(id=new_uuid(), code=str(code or "").strip().upper(),
                   name=str(name or "").strip(), rule_type=LoyaltyRuleType(rule_type),
                   created_by_user_id=created_by_user_id)
        if not rule.code or not rule.name:
            raise InvalidLoyaltyRuleError("La regla necesita código y nombre")
        rule._apply_definition(**definition)
        return rule

    def update(self, **definition) -> None:
        if self.status is LoyaltyRuleStatus.ACTIVE:
            raise InvalidLoyaltyRuleStateError(
                "Una regla activa no se edita: desactívala, corrígela y vuelve a activarla")
        if "name" in definition:
            nombre = str(definition.pop("name") or "").strip()
            if not nombre:
                raise InvalidLoyaltyRuleError("La regla necesita nombre")
            self.name = nombre
        self._apply_definition(**definition)
        self.updated_at = _now()

    def _apply_definition(self, *, priority: Any = None, program_id: str | None = None,
                          condition_definition: Any = None, benefit_definition: Any = None,
                          effective_from: str | None = None, effective_to: str | None = None,
                          stackable: Any = None, maximum_uses: Any = None,
                          customer_limit: Any = None, daily_limit: Any = None,
                          monthly_limit: Any = None, branch_scope: Any = None,
                          channel_scope: Any = None, payment_method_scope: Any = None,
                          product_scope: Any = None, category_scope: Any = None,
                          customer_segment_scope: Any = None) -> None:
        if self.rule_type not in SALE_EVALUATED_RULE_TYPES:
            raise InvalidLoyaltyRuleError(
                f"{self.rule_type.value} no se evalúa al cobrar: se otorga desde "
                f"{_OWN_FLOW.get(self.rule_type, 'su propio flujo')}")
        condicion = _parse_json(condition_definition, {}) if condition_definition is not None \
            else self.condition_definition
        validate_condition(condicion)
        beneficio = _parse_json(benefit_definition, None) if benefit_definition is not None \
            else self.benefit_definition
        beneficio = validate_benefit(self.rule_type, beneficio)
        if priority is not None:
            self.priority = int(priority)
        self.program_id = program_id or None if program_id is not None else self.program_id
        desde = effective_from if effective_from is not None else self.effective_from
        hasta = effective_to if effective_to is not None else self.effective_to
        desde, hasta = (desde or None), (hasta or None)
        if desde and hasta and str(hasta) < str(desde):
            raise InvalidLoyaltyRuleError("La vigencia termina antes de empezar")
        self.condition_definition = condicion
        self.benefit_definition = beneficio
        self.effective_from, self.effective_to = desde, hasta
        if stackable is not None:
            self.stackable = bool(stackable)
        for nombre, valor in (("maximum_uses", maximum_uses), ("customer_limit", customer_limit),
                              ("daily_limit", daily_limit), ("monthly_limit", monthly_limit)):
            if valor is not None:
                setattr(self, nombre, _limit(valor, nombre))
        alcances = {
            "branch_scope": (branch_scope, None),
            "channel_scope": (channel_scope, CHANNELS),
            "payment_method_scope": (payment_method_scope, PAYMENT_METHODS),
            "product_scope": (product_scope, None),
            "category_scope": (category_scope, None),
            "customer_segment_scope": (customer_segment_scope, None),
        }
        for nombre, (valor, permitidos) in alcances.items():
            if valor is not None:
                setattr(self, nombre, _scope(valor, nombre, permitidos))
        requerido = _REQUIRED_SCOPE.get(self.rule_type)
        if requerido and not getattr(self, requerido):
            raise InvalidLoyaltyRuleError(
                f"{self.rule_type.value} necesita su alcance ({requerido}): sin él "
                "multiplicaría toda la compra")

    # ── ciclo de vida ─────────────────────────────────────────────────────
    def activate(self, *, actor_user_id: str) -> None:
        if self.status is LoyaltyRuleStatus.ACTIVE:
            raise InvalidLoyaltyRuleStateError("La regla ya está activa")
        if actor_user_id == self.created_by_user_id:
            raise LoyaltySegregationOfDutiesError(
                "Quien crea la regla no puede activarla (§60): la activa otra persona")
        self.status = LoyaltyRuleStatus.ACTIVE
        self.activated_by_user_id = actor_user_id
        self.activated_at = self.updated_at = _now()

    def deactivate(self) -> None:
        if self.status is not LoyaltyRuleStatus.ACTIVE:
            raise InvalidLoyaltyRuleStateError("Sólo una regla activa se desactiva")
        self.status = LoyaltyRuleStatus.INACTIVE
        self.deactivated_at = self.updated_at = _now()

    def is_in_effect(self, moment_iso: str) -> bool:
        if self.status is not LoyaltyRuleStatus.ACTIVE:
            return False
        if self.effective_from and moment_iso[:len(self.effective_from)] < self.effective_from:
            return False
        if self.effective_to and moment_iso[:len(self.effective_to)] > self.effective_to:
            return False
        return True


def _parse_json(value: Any, default: Any) -> Any:
    if value in (None, ""):
        return default if default is not None else {}
    if isinstance(value, (dict, list)):
        return value
    try:
        return json.loads(str(value))
    except json.JSONDecodeError as exc:
        raise InvalidLoyaltyRuleError(f"Definición ilegible: {exc.msg}") from None


__all__ = ["CHANNELS", "CONDITION_FIELDS", "CONDITION_OPERATORS", "LoyaltyRule",
           "PAYMENT_METHODS", "validate_benefit", "validate_condition"]
