"""Reglas de Fidelidad ejecutadas por el POS (2026-10-03), contra el esquema real.

Decisión del usuario: "las reglas salen de Fidelidad y el POS las ejecuta".

* Las reglas se crean y activan en Fidelidad (otra persona activa, §60), con
  códigos de producto/categoría/sucursal que se traducen a identificadores.
* El cobro (`SALE_COMPLETED` por el bus) acredita con las reglas, guarda el
  desglose y cuenta los usos; reintentar el evento acredita lo mismo.
* El POS muestra como "puntos a ganar" el mismo cálculo.
* `EvaluateCustomerBenefitsQuery` (§25) resuelve cupones, vales y puntos con
  la combinación configurada (§24).
"""

from __future__ import annotations

import importlib
import sqlite3
from datetime import datetime, timezone
from decimal import Decimal

import pytest

from backend.application.loyalty.authorization import LoyaltyAuthorizationPolicy
from backend.application.loyalty.integrations.sales_events import SaleLoyaltyEventHandlers
from backend.application.loyalty.queries.customer_benefits_query import (
    CustomerBenefitsRequest,
    EvaluateCustomerBenefitsQuery,
    LoyaltyAccrualEvaluator,
)
from backend.application.loyalty.queries.redemption_preview_query import (
    LoyaltyRedemptionPreviewQuery,
)
from backend.application.loyalty.use_cases import rule_use_cases as ru
from backend.shared.ids import new_uuid

AUTH = LoyaltyAuthorizationPolicy.permissive_for_tests()
ANA, BETO, BRANCH = new_uuid(), new_uuid(), new_uuid()


@pytest.fixture(scope="module")
def template_db():
    import migrations.m000_base_schema as base
    from backend.infrastructure.db.schema.commercial_instruments_schema import (
        create_commercial_instruments_schema,
    )
    from backend.infrastructure.db.schema.loyalty_schema import create_loyalty_schema
    from backend.infrastructure.db.schema.products_schema import create_products_schema

    c = sqlite3.connect(":memory:")
    base.up(c)
    for crear in (create_loyalty_schema, create_commercial_instruments_schema):
        crear(c)
    try:
        create_products_schema(c)
    except Exception:   # noqa: BLE001 - el esquema base ya trae una tabla products legacy
        pass
    importlib.import_module("migrations.standalone.295_loyalty_rules_engine").run(c)
    c.commit()
    yield c
    c.close()


@pytest.fixture
def conn(template_db):
    c = sqlite3.connect(":memory:")
    template_db.backup(c)
    c.row_factory = sqlite3.Row
    _catalog(c)
    yield c
    c.close()


def _catalog(c):
    """Producto «Arrachera» en la subcategoría «Res» de «Carnes»: lo justo para
    alcances por código, sin depender de la forma completa del catálogo."""
    c.execute("DROP TABLE IF EXISTS products")
    c.execute("DROP TABLE IF EXISTS product_categories")
    c.execute("CREATE TABLE product_categories (id TEXT PRIMARY KEY, code TEXT, parent_id TEXT)")
    c.execute("CREATE TABLE products (id TEXT PRIMARY KEY, code TEXT, category_id TEXT)")
    c.executemany("INSERT INTO product_categories VALUES (?,?,?)",
                  [("cat-carnes", "CARNES", None), ("cat-res", "RES", "cat-carnes")])
    c.executemany("INSERT INTO products VALUES (?,?,?)",
                  [("p-arrachera", "ARR01", "cat-res"), ("p-refresco", "REF01", None)])
    c.commit()


def _ok(r):
    assert r.success, r.message
    return r


def _create(conn, code, rule_type, **form):
    return _ok(ru.CreateLoyaltyRuleUseCase(AUTH).execute(
        conn, code=code, name=code.title(), rule_type=rule_type, actor_user_id=ANA,
        actor_branch_id=BRANCH, operation_id=new_uuid(), form=form)).entity_id


def _activate(conn, rule_id, who=BETO):
    return ru.ActivateLoyaltyRuleUseCase(AUTH).execute(
        conn, rule_id=rule_id, actor_user_id=who, actor_branch_id=BRANCH, operation_id=new_uuid())


LINES = [{"product_id": "p-arrachera", "quantity": "1.5", "amount": "300"},
         {"product_id": "p-refresco", "quantity": "2", "amount": "100"}]


def _sale_event(customer, *, total="400", lines=LINES, sale_id=None):
    return {"event_id": new_uuid(), "entity_id": sale_id or new_uuid(), "branch_id": BRANCH,
            "user_id": new_uuid(),
            "timestamp": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "payload": {"customer_id": customer, "total": total, "channel": "POS",
                        "lines": lines, "payments": [{"method": "CARD", "amount": total}]}}


class TestRulesFromFidelidad:
    def test_creator_cannot_activate_and_codes_become_ids(self, conn):
        rid = _create(conn, "CARNES_X2", "CATEGORY_MULTIPLIER", multiplier=Decimal("2"),
                      category_codes="carnes")
        assert "activarla" in _activate(conn, rid, who=ANA).message
        _ok(_activate(conn, rid))
        fila = conn.execute("SELECT category_scope, status FROM loyalty_rules").fetchone()
        assert fila["category_scope"] == '["cat-carnes"]' and fila["status"] == "ACTIVE"

    def test_unknown_codes_are_an_error_not_ignored(self, conn):
        r = ru.CreateLoyaltyRuleUseCase(AUTH).execute(
            conn, code="X", name="X", rule_type="PRODUCT_MULTIPLIER", actor_user_id=ANA,
            actor_branch_id=BRANCH, operation_id=new_uuid(),
            form={"multiplier": Decimal("2"), "product_codes": "NOEXISTE"})
        assert not r.success and "NOEXISTE" in r.message

    def test_edit_keeps_what_is_left_blank(self, conn):
        rid = _create(conn, "FINDE", "FIXED_BONUS", points=Decimal("25"), weekdays="sáb, dom",
                      min_subtotal=Decimal("200"))
        _ok(ru.UpdateLoyaltyRuleUseCase(AUTH).execute(
            conn, rule_id=rid, actor_user_id=ANA, actor_branch_id=BRANCH,
            operation_id=new_uuid(), form={"priority": 150}))
        fila = conn.execute("SELECT priority, benefit_definition, condition_definition"
                            " FROM loyalty_rules").fetchone()
        assert fila["priority"] == 150 and '"25"' in fila["benefit_definition"]
        assert "weekday" in fila["condition_definition"]


class TestPosExecutesTheRules:
    def test_checkout_accrues_with_rules_and_records_breakdown(self, conn):
        _activate(conn, _create(conn, "CARNES_X2", "CATEGORY_MULTIPLIER",
                                multiplier=Decimal("2"), category_codes="CARNES"))
        _activate(conn, _create(conn, "PRIMERA", "FIRST_PURCHASE_BONUS", points=Decimal("50")))
        cliente = new_uuid()
        estimado = LoyaltyAccrualEvaluator(conn).evaluate(
            customer_id=cliente, branch_id=BRANCH, total="400", lines=LINES).points
        evento = _sale_event(cliente)
        SaleLoyaltyEventHandlers(conn).on_sale_completed(evento)
        # base 40 + carnes (300/400 de 40 = 30) + primera compra 50
        assert LoyaltyRedemptionPreviewQuery(conn).balance(cliente) == 120 == estimado
        SaleLoyaltyEventHandlers(conn).on_sale_completed(evento)   # reintento
        assert LoyaltyRedemptionPreviewQuery(conn).balance(cliente) == 120
        desglose = conn.execute("SELECT breakdown_json FROM loyalty_sale_evaluations").fetchone()[0]
        assert "CARNES_X2" in desglose and "PRIMERA" in desglose
        assert conn.execute("SELECT COUNT(*) FROM loyalty_rule_applications").fetchone()[0] == 2

        # Segunda compra: la primera compra ya no aplica (lo recuerda el historial).
        SaleLoyaltyEventHandlers(conn).on_sale_completed(_sale_event(cliente))
        assert LoyaltyRedemptionPreviewQuery(conn).balance(cliente) == 120 + 70

    def test_customer_limit_counts_real_uses(self, conn):
        _activate(conn, _create(conn, "UNA", "FIXED_BONUS", points=Decimal("10"),
                                customer_limit=1))
        cliente = new_uuid()
        for _ in range(2):
            SaleLoyaltyEventHandlers(conn).on_sale_completed(_sale_event(cliente, total="10",
                                                                         lines=[]))
        assert LoyaltyRedemptionPreviewQuery(conn).balance(cliente) == 1 + 10 + 1

    def test_deactivated_rule_stops_applying(self, conn):
        rid = _create(conn, "BONO", "FIXED_BONUS", points=Decimal("10"))
        _activate(conn, rid)
        _ok(ru.DeactivateLoyaltyRuleUseCase(AUTH).execute(
            conn, rule_id=rid, actor_user_id=ANA, actor_branch_id=BRANCH, operation_id=new_uuid()))
        assert LoyaltyAccrualEvaluator(conn).evaluate(
            customer_id=new_uuid(), branch_id=BRANCH, total="100").points == 10


class TestCustomerBenefitsContract:
    def _coupon(self, conn, value="30"):
        from backend.application.commercial_instruments.use_cases import coupon_use_cases as cu
        from backend.domain.commercial_instruments.enums import CommercialBenefitType, CouponType

        d = _ok(cu.CreateCouponDefinitionUseCase(AUTH).execute(
            conn, code=f"D{new_uuid()[-5:]}", name="Cupón", coupon_type=CouponType.PUBLIC_CODE,
            benefit_type=CommercialBenefitType.FIXED_AMOUNT, benefit_value=Decimal(value),
            actor_user_id=ANA, operation_id=new_uuid())).entity_id
        i = _ok(cu.IssueCouponInstanceUseCase(AUTH).execute(
            conn, definition_id=d, code=f"C{new_uuid()[-6:]}", actor_user_id=ANA,
            actor_branch_id=BRANCH, operation_id=new_uuid())).entity_id
        return conn.execute("SELECT code FROM coupon_instances WHERE id=?", (i,)).fetchone()[0]

    def test_one_coupon_per_sale_by_default_and_points_preview(self, conn):
        cliente = new_uuid()
        SaleLoyaltyEventHandlers(conn).on_sale_completed(_sale_event(cliente, total="5000",
                                                                     lines=[]))
        c1, c2 = self._coupon(conn), self._coupon(conn, "50")
        r = EvaluateCustomerBenefitsQuery(conn).execute(CustomerBenefitsRequest(
            customer_id=cliente, branch_id=BRANCH, subtotal=Decimal("400"),
            sale_lines=tuple(LINES), payment_method="CASH", coupon_codes=(c1, c2, "NOPE"),
            requested_points=100))
        assert [b["kind"] for b in r.eligible_benefits] == ["COUPON", "POINTS"]
        motivos = {b["reference"]: b["reason"] for b in r.ineligible_benefits}
        assert motivos["NOPE"] == "El cupón no existe" and len(motivos) == 2
        assert r.points_to_redeem == 100
        # Acumula sobre lo pagado: 400 - 30 cupón - 10 de puntos = 360 → 36
        assert r.points_to_earn == 36
        assert r.financial_effects_preview["points_liability_to_recognize"] == "3.60"

    def test_configured_stacking_is_applied(self, conn):
        _ok(ru.ConfigureStackingUseCase(AUTH).execute(
            conn, combination="POINTS_COUPON", option="BEST_BENEFIT_ONLY", actor_user_id=ANA,
            actor_branch_id=BRANCH, operation_id=new_uuid()))
        cliente = new_uuid()
        SaleLoyaltyEventHandlers(conn).on_sale_completed(_sale_event(cliente, total="5000",
                                                                     lines=[]))
        r = EvaluateCustomerBenefitsQuery(conn).execute(CustomerBenefitsRequest(
            customer_id=cliente, branch_id=BRANCH, subtotal=Decimal("400"),
            coupon_codes=(self._coupon(conn, "30"),), requested_points=500))
        assert [b["kind"] for b in r.eligible_benefits] == ["POINTS"]   # $50 > $30
        bad = ru.ConfigureStackingUseCase(AUTH).execute(
            conn, combination="POINTS_COUPON", option="ALLOW_WITH_LIMIT", actor_user_id=ANA,
            actor_branch_id=BRANCH, operation_id=new_uuid())
        assert not bad.success and "tope" in bad.message
