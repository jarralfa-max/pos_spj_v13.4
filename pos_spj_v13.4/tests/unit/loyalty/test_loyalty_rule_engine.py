"""Motor de reglas de acumulación (§13) y política de combinación (§24),
2026-10-03 — puros, sin base de datos.

Decisión del usuario: "las reglas salen de Fidelidad y el POS las ejecuta".
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from backend.domain.loyalty.entities.loyalty_rule import LoyaltyRule
from backend.domain.loyalty.enums import (
    LoyaltyRuleType as T,
    StackingCombination as SC,
    StackingOption as SO,
)
from backend.domain.loyalty.exceptions import (
    InvalidLoyaltyRuleError,
    InvalidLoyaltyRuleStateError,
    LoyaltySegregationOfDutiesError,
)
from backend.domain.loyalty.policies.stacking_policy import Benefit, StackingPolicy, StackingSetting
from backend.domain.loyalty.services.rule_engine import (
    AccrualContext,
    AccrualLine,
    LoyaltyRuleEngine,
    RuleUsage,
)

SAT = datetime(2026, 10, 3, 12, 0, tzinfo=timezone.utc)   # sábado
CREATOR, APPROVER = "u-creador", "u-aprobador"


def _rule(code, rule_type, benefit, *, active=True, **kw) -> LoyaltyRule:
    regla = LoyaltyRule.create(code=code, name=code.title(), rule_type=rule_type,
                               created_by_user_id=CREATOR, benefit_definition=benefit, **kw)
    if active:
        regla.activate(actor_user_id=APPROVER)
    return regla


def _ctx(amount="100", lines=None, **kw) -> AccrualContext:
    lines = lines if lines is not None else (
        AccrualLine("carne", Decimal("2"), Decimal("60"), frozenset({"cat-carnes", "cat-raiz"})),
        AccrualLine("refresco", Decimal("4"), Decimal("40"), frozenset({"cat-bebidas"})))
    kw.setdefault("customer_id", "c1")
    kw.setdefault("branch_id", "b1")
    return AccrualContext(occurred_at=kw.pop("occurred_at", SAT),
                          eligible_amount=Decimal(amount), lines=tuple(lines), **kw)


ENGINE = LoyaltyRuleEngine(pesos_per_point=Decimal("10"))


class TestBaseAndCompatibility:
    def test_without_rules_it_accrues_exactly_like_before(self):
        r = ENGINE.evaluate([], _ctx("157.90"))
        assert r.points == 15
        assert [a.code for a in r.applied] == ["BASE"]

    def test_unscoped_base_rule_replaces_the_configuration(self):
        regla = _rule("DOBLE", T.POINTS_PER_AMOUNT, {"amount": "5", "points": "1"})
        assert ENGINE.evaluate([regla], _ctx("100")).points == 20

    def test_scoped_base_rule_covers_its_lines_and_configuration_the_rest(self):
        carnes = _rule("CARNES", T.POINTS_PER_AMOUNT, {"amount": "5", "points": "1"},
                       category_scope=["cat-raiz"])   # alcanza la subcategoría
        r = ENGINE.evaluate([carnes], _ctx("100"))
        # carnes: 60/5 = 12; resto (40) con la base: 4
        assert {a.code: a.points for a in r.applied} == {"CARNES": 12, "BASE": 4}

    def test_points_per_unit(self):
        regla = _rule("UNIDAD", T.POINTS_PER_UNIT, {"points": "3"}, product_scope=["refresco"])
        r = ENGINE.evaluate([regla], _ctx())
        assert {a.code: a.points for a in r.applied} == {"UNIDAD": 12, "BASE": 6}


class TestMultipliersAndBonuses:
    def test_category_multiplier_only_multiplies_its_share(self):
        regla = _rule("X2CARNE", T.CATEGORY_MULTIPLIER, {"multiplier": "2"},
                      category_scope=["cat-carnes"])
        r = ENGINE.evaluate([regla], _ctx("100"))
        assert r.points == 10 + 6

    def test_branch_and_payment_multipliers(self):
        sucursal = _rule("X3SUC", T.BRANCH_MULTIPLIER, {"multiplier": "3"}, branch_scope=["b1"])
        tarjeta = _rule("X2TAR", T.PAYMENT_METHOD_MULTIPLIER, {"multiplier": "2"},
                        payment_method_scope=["CARD"])
        ctx = _ctx("100", payments=(("CARD", Decimal("50")), ("CASH", Decimal("50"))))
        r = ENGINE.evaluate([sucursal, tarjeta], ctx)
        assert {a.code: a.points for a in r.applied} == {"BASE": 10, "X3SUC": 20, "X2TAR": 5}
        otra = ENGINE.evaluate([sucursal], _ctx("100", branch_id="b2"))
        assert otra.points == 10 and otra.rejected[0].reason == "Sucursal fuera del alcance"

    def test_first_purchase_and_visit_frequency(self):
        primera = _rule("PRIMERA", T.FIRST_PURCHASE_BONUS, {"points": "50"})
        frecuencia = _rule("FREC", T.VISIT_FREQUENCY_BONUS,
                           {"points": "20", "visits": "3", "days": "30"})
        nuevo = ENGINE.evaluate([primera, frecuencia], _ctx("100"))
        assert {a.code: a.points for a in nuevo.applied} == {"BASE": 10, "PRIMERA": 50}
        previas = (SAT - timedelta(days=3), SAT - timedelta(days=10))
        frecuente = ENGINE.evaluate([primera, frecuencia], _ctx("100", previous_purchases=previas))
        assert {a.code: a.points for a in frecuente.applied} == {"BASE": 10, "FREC": 20}

    def test_condition_minimum_and_weekday(self):
        fin = _rule("FINDE", T.FIXED_BONUS, {"points": "25"}, condition_definition={
            "all": [{"field": "subtotal", "op": "gte", "value": "200"},
                    {"field": "weekday", "op": "in", "value": [5, 6]}]})
        assert ENGINE.evaluate([fin], _ctx("150")).points == 15
        assert ENGINE.evaluate([fin], _ctx("250")).points == 25 + 25

    def test_program_and_segment_scopes(self):
        vip = _rule("VIP", T.FIXED_BONUS, {"points": "10"}, program_id="p-vip",
                    customer_segment_scope=["seg-oro"])
        assert ENGINE.evaluate([vip], _ctx(program_ids=frozenset({"p-vip"}))).points == 10
        dentro = _ctx(program_ids=frozenset({"p-vip"}), segment_ids=frozenset({"seg-oro"}))
        assert ENGINE.evaluate([vip], dentro).points == 20


class TestSelectionAndLimits:
    def test_non_stackable_higher_priority_blocks_the_rest(self):
        exclusiva = _rule("EXCL", T.FIXED_BONUS, {"points": "100"}, priority=200, stackable=False)
        otra = _rule("OTRA", T.FIXED_BONUS, {"points": "5"}, priority=100)
        r = ENGINE.evaluate([otra, exclusiva], _ctx("100"))
        assert {a.code for a in r.applied} == {"BASE", "EXCL"}
        assert [x.code for x in r.rejected] == ["OTRA"]

    def test_non_stackable_lower_priority_does_not_apply_after_others(self):
        alta = _rule("ALTA", T.FIXED_BONUS, {"points": "5"}, priority=200)
        sola = _rule("SOLA", T.FIXED_BONUS, {"points": "50"}, priority=100, stackable=False)
        r = ENGINE.evaluate([alta, sola], _ctx("100"))
        assert {a.code for a in r.applied} == {"BASE", "ALTA"}

    def test_limits_and_window(self):
        regla = _rule("LIM", T.FIXED_BONUS, {"points": "5"}, customer_limit=2, daily_limit=1,
                      effective_from="2026-10-01", effective_to="2026-10-31")
        assert ENGINE.evaluate([regla], _ctx(), {regla.id: RuleUsage(customer_today=1)}).points == 10
        assert ENGINE.evaluate([regla], _ctx(), {regla.id: RuleUsage(customer=2)}).points == 10
        assert ENGINE.evaluate([regla], _ctx(occurred_at=SAT + timedelta(days=40))).points == 10
        assert ENGINE.evaluate([regla], _ctx()).points == 15

    def test_draft_rules_do_not_apply(self):
        borrador = _rule("BORR", T.FIXED_BONUS, {"points": "5"}, active=False)
        assert ENGINE.evaluate([borrador], _ctx()).points == 10


class TestRuleDefinition:
    def test_types_granted_elsewhere_are_rejected(self):
        with pytest.raises(InvalidLoyaltyRuleError, match="Referidos"):
            LoyaltyRule.create(code="X", name="X", rule_type=T.REFERRAL_BONUS,
                               created_by_user_id=CREATOR, benefit_definition={"points": "5"})

    def test_multiplier_needs_its_scope_and_sane_values(self):
        with pytest.raises(InvalidLoyaltyRuleError, match="alcance"):
            _rule("M", T.CATEGORY_MULTIPLIER, {"multiplier": "2"})
        with pytest.raises(InvalidLoyaltyRuleError, match="10"):
            _rule("M", T.BRANCH_MULTIPLIER, {"multiplier": "50"}, branch_scope=["b1"])

    def test_condition_language_is_closed_no_code(self):
        for mala in ({"field": "__import__('os')", "op": "eq", "value": "1"},
                     {"field": "subtotal", "op": "exec", "value": "1"},
                     {"script": "x"}, {"field": "subtotal", "op": "gt", "value": 1.5}):
            with pytest.raises(InvalidLoyaltyRuleError):
                _rule("C", T.FIXED_BONUS, {"points": "1"}, condition_definition=mala)

    def test_creator_cannot_activate_and_active_rules_are_not_edited(self):
        regla = _rule("S", T.FIXED_BONUS, {"points": "1"}, active=False)
        with pytest.raises(LoyaltySegregationOfDutiesError):
            regla.activate(actor_user_id=CREATOR)
        regla.activate(actor_user_id=APPROVER)
        with pytest.raises(InvalidLoyaltyRuleStateError):
            regla.update(priority=5)


class TestStacking:
    def _b(self, kind, value, ref=None):
        return Benefit(kind, ref or kind.lower(), Decimal(value), kind)

    def test_unconfigured_combinations_are_allowed(self):
        r = StackingPolicy().resolve([self._b("COUPON", "20"), self._b("POINTS", "10")])
        assert len(r.accepted) == 2

    def test_each_option(self):
        def run(opcion, *beneficios, **extra):
            ajuste = StackingSetting(SC.POINTS_COUPON, opcion, **extra)
            return StackingPolicy([ajuste]).resolve(beneficios)

        cupon, puntos = self._b("COUPON", "20"), self._b("POINTS", "30")
        assert [b.kind for b in run(SO.DENY, cupon, puntos).accepted] == ["COUPON"]
        assert [b.kind for b in run(SO.EXCLUSIVE, cupon, puntos).accepted] == ["POINTS"]
        assert [b.kind for b in run(SO.BEST_BENEFIT_ONLY, cupon, puntos).accepted] == ["POINTS"]
        con_tope = run(SO.ALLOW_WITH_LIMIT, cupon, puntos, limit_value=Decimal("25"))
        assert [(b.kind, b.value) for b in con_tope.accepted] == [
            ("COUPON", Decimal("20")), ("POINTS", Decimal("5"))]
        prioridad = run(SO.PRIORITY_ORDER, puntos, cupon, priority_order=("COUPON", "POINTS"))
        assert [b.kind for b in prioridad.accepted] == ["COUPON"]

    def test_one_coupon_per_sale(self):
        politica = StackingPolicy([StackingSetting(SC.COUPON_COUPON, SO.DENY)])
        r = politica.resolve([self._b("COUPON", "10", "c1"), self._b("COUPON", "15", "c2")])
        assert [b.reference for b in r.accepted] == ["c1"]
        assert r.rejected[0][0].reference == "c2"


class TestBirthdayAndReturns:
    def test_birthday_bonus_in_its_window(self):
        bono = _rule("CUMPLE", T.BIRTHDAY_BONUS, {"points": "100", "window_days": "3"})
        assert ENGINE.evaluate([bono], _ctx("100", days_to_birthday=2)).points == 110
        assert ENGINE.evaluate([bono], _ctx("100", days_to_birthday=5)).points == 10
        assert ENGINE.evaluate([bono], _ctx("100")).points == 10   # sin cumpleaños registrado
        doble = _rule("CUMPLEX2", T.BIRTHDAY_BONUS, {"multiplier": "2"})
        assert ENGINE.evaluate([doble], _ctx("100", days_to_birthday=0)).points == 20

    def test_fixed_bonus_condition_after_a_return(self):
        from backend.domain.loyalty.services.rule_engine import condition_holds_for_subtotal

        condicion = {"all": [{"field": "subtotal", "op": "gte", "value": "200"},
                             {"field": "weekday", "op": "in", "value": [5, 6]}]}
        assert condition_holds_for_subtotal(condicion, Decimal("250"))
        assert not condition_holds_for_subtotal(condicion, Decimal("150"))
        assert condition_holds_for_subtotal({}, Decimal("0"))
