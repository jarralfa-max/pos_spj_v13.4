"""Reglas de acumulación (§13) y combinación de beneficios (§24), 2026-10-03.

Las reglas son parte de la definición del programa, así que usan sus permisos:
crear/editar = `programa.editar`, activar = `programa.aprobar` (y la activa
OTRA persona, §60), desactivar = `programa.suspender`. La combinación de
beneficios es configuración: `configuracion.editar`.
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation

from backend.application.loyalty.permissions import LoyaltyPermissions as LP
from backend.application.loyalty.result import LoyaltyResult, fail_from_domain_error
from backend.application.loyalty.use_cases._base import _LoyaltyBaseUseCase
from backend.domain.loyalty.entities.loyalty_rule import LoyaltyRule
from backend.domain.loyalty.enums import StackingCombination, StackingOption
from backend.domain.loyalty.exceptions import InvalidLoyaltyRuleError, LoyaltyDomainError
from backend.domain.loyalty.policies.stacking_policy import BENEFIT_KINDS, StackingSetting
from backend.infrastructure.db.repositories.loyalty.rule_repository import LoyaltyRuleRepository
from backend.infrastructure.db.repositories.loyalty.unit_of_work import LoyaltyUnitOfWork

_DEFINITION_KEYS = (
    "priority", "program_id", "condition_definition", "benefit_definition", "effective_from",
    "effective_to", "stackable", "maximum_uses", "customer_limit", "daily_limit",
    "monthly_limit", "branch_scope", "channel_scope", "payment_method_scope", "product_scope",
    "category_scope", "customer_segment_scope",
)


def _definition(values: dict) -> dict:
    return {k: v for k, v in values.items() if k in _DEFINITION_KEYS}


_WEEKDAYS = {"lun": 0, "mar": 1, "mie": 2, "mié": 2, "jue": 3, "vie": 4, "sab": 5, "sáb": 5,
             "dom": 6}


def _items(text) -> list[str]:
    if not text:
        return []
    if isinstance(text, (list, tuple)):
        return [str(t).strip() for t in text if str(t).strip()]
    return [t.strip() for t in str(text).replace(";", ",").split(",") if t.strip()]


def _set(value) -> bool:
    return value not in (None, "", 0, Decimal("0"))


def rule_definition_from_form(connection, rule_type, form: dict) -> dict:
    """Formulario de la pantalla → definición declarativa de `LoyaltyRule`.

    La persona escribe puntos, montos, multiplicador, compra mínima, días y
    códigos; aquí se arman el beneficio, la condición y los alcances, y los
    códigos se traducen a identificadores (uno inexistente es un error, no se
    ignora)."""
    from backend.domain.loyalty.enums import LoyaltyRuleType
    from backend.infrastructure.db.repositories.loyalty.rule_repository import (
        LoyaltyRuleScopeResolver,
    )

    tipo = LoyaltyRuleType(getattr(rule_type, "value", rule_type))
    beneficio: dict[str, str] = {}
    if tipo is LoyaltyRuleType.POINTS_PER_AMOUNT:
        beneficio = {"amount": str(form.get("amount") or ""), "points": str(form.get("points") or "")}
    elif tipo.value.endswith("_MULTIPLIER") or (
            tipo is LoyaltyRuleType.CAMPAIGN_BONUS and _set(form.get("multiplier"))):
        beneficio = {"multiplier": str(form.get("multiplier") or "")}
    elif tipo is LoyaltyRuleType.BIRTHDAY_BONUS:
        beneficio = ({"multiplier": str(form.get("multiplier"))} if _set(form.get("multiplier"))
                     else {"points": str(form.get("points") or "")})
        if _set(form.get("window_days")):
            beneficio["window_days"] = str(form["window_days"])
    elif tipo is LoyaltyRuleType.VISIT_FREQUENCY_BONUS:
        beneficio = {"points": str(form.get("points") or ""), "visits": str(form.get("visits") or ""),
                     "days": str(form.get("days") or "")}
    else:
        beneficio = {"points": str(form.get("points") or "")}

    hojas = []
    if _set(form.get("min_subtotal")):
        hojas.append({"field": "subtotal", "op": "gte", "value": str(form["min_subtotal"])})
    dias = _items(form.get("weekdays"))
    if dias:
        fuera = [d for d in dias if d.lower()[:3] not in _WEEKDAYS]
        if fuera:
            raise LoyaltyDomainError(f"Días no reconocidos: {', '.join(fuera)} (usa lun, mar, mié…)")
        hojas.append({"field": "weekday", "op": "in",
                      "value": sorted({_WEEKDAYS[d.lower()[:3]] for d in dias})})
    condicion = {"all": hojas} if hojas else {}
    if form.get("condition_definition"):
        import json

        avanzada = json.loads(str(form["condition_definition"]))
        condicion = {"all": [condicion, avanzada]} if condicion else avanzada

    resolver = LoyaltyRuleScopeResolver(connection)
    definicion: dict = {}
    # Editar sin tocar el beneficio o la condición los conserva.
    if any(k in form for k in ("points", "amount", "multiplier", "visits", "days",
                                "window_days")):
        definicion["benefit_definition"] = beneficio
    if any(k in form for k in ("min_subtotal", "weekdays", "condition_definition")):
        definicion["condition_definition"] = condicion
    for campo, tipo_alcance, destino in (("product_codes", "product", "product_scope"),
                                          ("category_codes", "category", "category_scope"),
                                          ("branch_names", "branch", "branch_scope"),
                                          ("segment_codes", "segment", "customer_segment_scope")):
        if campo in form:
            ids, faltan = resolver.resolve(tipo_alcance, _items(form.get(campo)))
            if faltan:
                raise LoyaltyDomainError(f"No se encontró: {', '.join(faltan)}")
            definicion[destino] = ids
    if "channels" in form:
        definicion["channel_scope"] = [c.upper() for c in _items(form.get("channels"))]
    if "payment_methods" in form:
        definicion["payment_method_scope"] = [c.upper() for c in _items(form.get("payment_methods"))]
    for campo in ("priority", "program_id", "effective_from", "effective_to", "stackable",
                  "maximum_uses", "customer_limit", "daily_limit", "monthly_limit"):
        if campo in form:
            definicion[campo] = form[campo]
    if not _set(definicion.get("priority")):
        definicion.pop("priority", None)
    return definicion


class CreateLoyaltyRuleUseCase(_LoyaltyBaseUseCase):
    def execute(self, connection, *, code: str, name: str, rule_type, actor_user_id: str,
                actor_branch_id: str, operation_id: str, form: dict | None = None,
                **definition) -> LoyaltyResult:
        try:
            self._auth.require(actor_user_id, LP.PROGRAM_EDIT)
            if form is not None:
                definition = rule_definition_from_form(connection, rule_type, form)
            with LoyaltyUnitOfWork(connection) as uow:
                reglas = LoyaltyRuleRepository(uow.connection)
                if reglas.get_by_code(code) is not None:
                    raise InvalidLoyaltyRuleError(f"Ya existe una regla con el código {code}")
                regla = LoyaltyRule.create(code=code, name=name, rule_type=rule_type,
                                           created_by_user_id=actor_user_id,
                                           **_definition(definition))
                reglas.save(regla)
                self._audit(uow, "LOYALTY_RULE_CREATED", entity_id=regla.id,
                            operation_id=operation_id, branch_id=actor_branch_id,
                            actor_user_id=actor_user_id, code=regla.code,
                            rule_type=regla.rule_type.value)
        except (LoyaltyDomainError, ValueError) as exc:
            return fail_from_domain_error(exc, operation_id=operation_id)
        return LoyaltyResult.ok("Regla creada en borrador; la activa otra persona.",
                                entity_id=regla.id, operation_id=operation_id)


class UpdateLoyaltyRuleUseCase(_LoyaltyBaseUseCase):
    def execute(self, connection, *, rule_id: str, actor_user_id: str, actor_branch_id: str,
                operation_id: str, name: str | None = None, form: dict | None = None,
                **definition) -> LoyaltyResult:
        try:
            self._auth.require(actor_user_id, LP.PROGRAM_EDIT)
            with LoyaltyUnitOfWork(connection) as uow:
                reglas = LoyaltyRuleRepository(uow.connection)
                regla = reglas.get(rule_id)
                if regla is None:
                    raise InvalidLoyaltyRuleError("La regla no existe")
                if form is not None:
                    definition = rule_definition_from_form(connection, regla.rule_type, form)
                cambios = _definition({k: v for k, v in definition.items() if v is not None})
                if name:
                    cambios["name"] = name
                regla.update(**cambios)
                reglas.save(regla)
                self._audit(uow, "LOYALTY_RULE_UPDATED", entity_id=regla.id,
                            operation_id=operation_id, branch_id=actor_branch_id,
                            actor_user_id=actor_user_id, fields=sorted(cambios))
        except (LoyaltyDomainError, ValueError) as exc:
            return fail_from_domain_error(exc, operation_id=operation_id)
        return LoyaltyResult.ok("Regla actualizada.", entity_id=rule_id, operation_id=operation_id)


class ActivateLoyaltyRuleUseCase(_LoyaltyBaseUseCase):
    def execute(self, connection, *, rule_id: str, actor_user_id: str, actor_branch_id: str,
                operation_id: str) -> LoyaltyResult:
        try:
            self._auth.require(actor_user_id, LP.PROGRAM_APPROVE)
            with LoyaltyUnitOfWork(connection) as uow:
                reglas = LoyaltyRuleRepository(uow.connection)
                regla = reglas.get(rule_id)
                if regla is None:
                    raise InvalidLoyaltyRuleError("La regla no existe")
                regla.activate(actor_user_id=actor_user_id)
                reglas.save(regla)
                self._audit(uow, "LOYALTY_RULE_ACTIVATED", entity_id=regla.id,
                            operation_id=operation_id, branch_id=actor_branch_id,
                            actor_user_id=actor_user_id, code=regla.code)
        except LoyaltyDomainError as exc:
            return fail_from_domain_error(exc, operation_id=operation_id)
        return LoyaltyResult.ok("Regla activa: el POS la aplica desde la siguiente venta.",
                                entity_id=rule_id, operation_id=operation_id)


class DeactivateLoyaltyRuleUseCase(_LoyaltyBaseUseCase):
    def execute(self, connection, *, rule_id: str, actor_user_id: str, actor_branch_id: str,
                operation_id: str) -> LoyaltyResult:
        try:
            self._auth.require(actor_user_id, LP.PROGRAM_SUSPEND)
            with LoyaltyUnitOfWork(connection) as uow:
                reglas = LoyaltyRuleRepository(uow.connection)
                regla = reglas.get(rule_id)
                if regla is None:
                    raise InvalidLoyaltyRuleError("La regla no existe")
                regla.deactivate()
                reglas.save(regla)
                self._audit(uow, "LOYALTY_RULE_DEACTIVATED", entity_id=regla.id,
                            operation_id=operation_id, branch_id=actor_branch_id,
                            actor_user_id=actor_user_id, code=regla.code)
        except LoyaltyDomainError as exc:
            return fail_from_domain_error(exc, operation_id=operation_id)
        return LoyaltyResult.ok("Regla desactivada.", entity_id=rule_id, operation_id=operation_id)


class ConfigureStackingUseCase(_LoyaltyBaseUseCase):
    def execute(self, connection, *, combination, option, actor_user_id: str,
                actor_branch_id: str, operation_id: str, limit_value=None,
                priority_order=None) -> LoyaltyResult:
        try:
            self._auth.require(actor_user_id, LP.CONFIG_EDIT)
            combinacion = StackingCombination(getattr(combination, "value", combination))
            opcion = StackingOption(getattr(option, "value", option))
            tope = None
            if opcion is StackingOption.ALLOW_WITH_LIMIT:
                try:
                    tope = Decimal(str(limit_value))
                except (InvalidOperation, ValueError):
                    tope = None
                if tope is None or isinstance(limit_value, float) or tope <= 0:
                    raise LoyaltyDomainError("«Permitir con tope» necesita un tope mayor a cero")
            orden: tuple[str, ...] = ()
            if opcion is StackingOption.PRIORITY_ORDER:
                crudo = priority_order or ""
                partes = crudo if isinstance(crudo, (list, tuple)) else str(crudo).split(",")
                orden = tuple(p.strip().upper() for p in partes if str(p).strip())
                fuera = [p for p in orden if p not in BENEFIT_KINDS]
                if not orden or fuera:
                    raise LoyaltyDomainError(
                        "«Orden de prioridad» necesita los tipos en orden, de: "
                        + ", ".join(BENEFIT_KINDS))
            with LoyaltyUnitOfWork(connection) as uow:
                LoyaltyRuleRepository(uow.connection).save_stacking(
                    StackingSetting(combinacion, opcion, tope, orden), actor_user_id=actor_user_id)
                self._audit(uow, "LOYALTY_STACKING_CONFIGURED", entity_id=combinacion.value,
                            operation_id=operation_id, branch_id=actor_branch_id,
                            actor_user_id=actor_user_id, option=opcion.value,
                            limit_value=str(tope) if tope is not None else None)
        except (LoyaltyDomainError, ValueError) as exc:
            return fail_from_domain_error(exc, operation_id=operation_id)
        return LoyaltyResult.ok("Combinación configurada.", entity_id=combinacion.value,
                                operation_id=operation_id)


__all__ = ["ActivateLoyaltyRuleUseCase", "ConfigureStackingUseCase", "CreateLoyaltyRuleUseCase",
           "DeactivateLoyaltyRuleUseCase", "UpdateLoyaltyRuleUseCase"]
