"""Pendientes de Fidelidad cerrados el 2026-10-03, contra el esquema real.

Decisiones del usuario:

* Fecha de nacimiento OPCIONAL y con consentimiento en Clientes; habilita el
  bono de cumpleaños de las reglas y el beneficio de cumpleaños del programa
  (una vez al año, dentro de su ventana).
* La recompensa de PRODUCTO descuenta inventario de la sucursal que entrega y
  su costo se asienta (costo de venta contra inventario).
* Devolución con bonos: base y multiplicadores en proporción; el bono fijo sólo
  si lo que queda deja de cumplir o la devolución es total.
"""

from __future__ import annotations

import importlib
import sqlite3
from datetime import date, datetime, timezone
from decimal import Decimal

import pytest

from backend.application.customers.authorization import CustomerAuthorizationPolicy
from backend.application.loyalty.authorization import LoyaltyAuthorizationPolicy
from backend.application.loyalty.integrations.sales_events import SaleLoyaltyEventHandlers
from backend.application.loyalty.queries.redemption_preview_query import (
    LoyaltyRedemptionPreviewQuery,
)
from backend.application.loyalty.use_cases import rule_use_cases as ru
from backend.shared.ids import new_uuid

AUTH = LoyaltyAuthorizationPolicy.permissive_for_tests()
CAUTH = CustomerAuthorizationPolicy.permissive_for_tests()
ANA, BETO = new_uuid(), new_uuid()


@pytest.fixture
def conn():
    import migrations.m000_base_schema as base
    from backend.application.services.finance.finance_bootstrap import bootstrap_finance
    from backend.infrastructure.db.schema.commercial_instruments_schema import (
        create_commercial_instruments_schema,
    )
    from backend.infrastructure.db.schema.customers_crm_schema import create_customers_crm_schema
    from backend.infrastructure.db.schema.finance_schema import create_finance_schema
    from backend.infrastructure.db.schema.inventory_schema import create_inventory_schema
    from backend.infrastructure.db.schema.loyalty_finance_schema import (
        create_loyalty_finance_tables,
    )
    from backend.infrastructure.db.schema.loyalty_schema import create_loyalty_schema
    from backend.infrastructure.db.schema.pricing_schema import create_pricing_schema
    from backend.infrastructure.db.schema.products_schema import create_products_schema

    c = sqlite3.connect(":memory:")
    base.up(c)
    c.execute("DROP TABLE IF EXISTS products")
    for crear in (create_products_schema, create_pricing_schema, create_inventory_schema,
                  create_customers_crm_schema, create_loyalty_schema,
                  create_commercial_instruments_schema, create_finance_schema,
                  create_loyalty_finance_tables):
        crear(c)
    for numero in ("295_loyalty_rules_engine", "297_loyalty_rewards_birthdays"):
        importlib.import_module(f"migrations.standalone.{numero}").run(c)
    bootstrap_finance(c)
    c.commit()
    c.row_factory = sqlite3.Row
    yield c
    c.close()


def _ok(r):
    assert r.success, r.message
    return r


def _customer(conn, name="Ana Torres") -> str:
    from backend.application.customers.use_cases.lifecycle_use_cases import CreateCustomerUseCase

    return _ok(CreateCustomerUseCase(CAUTH).execute(
        conn, actor_user_id=ANA, display_name=name, operation_id=new_uuid())).entity_id


def _set_birthday(conn, customer, month, day, consent=True):
    from backend.application.customers.use_cases.birthday_use_cases import (
        SetCustomerBirthdayUseCase,
    )
    return SetCustomerBirthdayUseCase(CAUTH).execute(
        conn, actor_user_id=ANA, customer_id=customer, operation_id=new_uuid(), month=month,
        day=day, consent=consent)


def _sale(conn, customer, total, *, when=None, sale_id=None):
    evento = {"event_id": new_uuid(), "entity_id": sale_id or new_uuid(), "branch_id": new_uuid(),
              "user_id": new_uuid(),
              "timestamp": (when or datetime.now(timezone.utc)).isoformat(timespec="seconds"),
              "payload": {"customer_id": customer, "total": total, "channel": "POS",
                          "payments": [{"method": "CASH", "amount": total}]}}
    SaleLoyaltyEventHandlers(conn).on_sale_completed(evento)
    return evento["entity_id"]


def _points(conn, customer):
    return LoyaltyRedemptionPreviewQuery(conn).balance(customer)


class TestCustomerBirthday:
    def test_birthday_needs_consent_and_removing_consent_deletes_it(self, conn):
        from backend.application.customers.use_cases.birthday_use_cases import customer_birthday

        cliente = _customer(conn)
        r = _set_birthday(conn, cliente, 5, 17, consent=False)
        assert not r.success and r.error_code == "CONSENT_REQUIRED"
        assert customer_birthday(conn, cliente) is None
        _ok(_set_birthday(conn, cliente, 5, 17))
        assert (customer_birthday(conn, cliente).month, customer_birthday(conn, cliente).day) == (5, 17)
        assert not _set_birthday(conn, cliente, 2, 30).success
        _ok(_set_birthday(conn, cliente, None, None, consent=False))
        assert customer_birthday(conn, cliente) is None

    def test_birthday_rule_applies_on_the_customer_birthday(self, conn):
        hoy = date.today()
        rid = _ok(ru.CreateLoyaltyRuleUseCase(AUTH).execute(
            conn, code="CUMPLE", name="Cumpleaños", rule_type="BIRTHDAY_BONUS", actor_user_id=ANA,
            actor_branch_id=new_uuid(), operation_id=new_uuid(),
            form={"points": Decimal("50")})).entity_id
        _ok(ru.ActivateLoyaltyRuleUseCase(AUTH).execute(
            conn, rule_id=rid, actor_user_id=BETO, actor_branch_id=new_uuid(),
            operation_id=new_uuid()))
        sin_cumple, con_cumple = _customer(conn, "Sin"), _customer(conn, "Con")
        _ok(_set_birthday(conn, con_cumple, hoy.month, min(hoy.day, 28)))
        _sale(conn, sin_cumple, "100")
        _sale(conn, con_cumple, "100")
        assert _points(conn, sin_cumple) == 10
        assert _points(conn, con_cumple) == (60 if hoy.day <= 28 else 10)

    def test_program_birthday_benefit_is_granted_once_a_year(self, conn):
        from backend.application.loyalty.use_cases.birthday_use_cases import (
            GrantDueBirthdayBenefitsUseCase,
        )
        from backend.application.loyalty.use_cases import birthday_use_cases as bu
        from backend.application.loyalty.use_cases import membership_use_cases as mu
        from backend.application.loyalty.use_cases import program_use_cases as pu
        from backend.domain.loyalty.enums import BirthdayBenefitType

        programa = _ok(pu.CreateLoyaltyProgramUseCase(AUTH).execute(
            conn, code="P1", name="Puntos", currency_name="Puntos", actor_user_id=ANA,
            actor_branch_id=new_uuid(), operation_id=new_uuid())).entity_id
        _ok(pu.ApproveLoyaltyProgramUseCase(AUTH).execute(
            conn, program_id=programa, actor_user_id=BETO, actor_branch_id=new_uuid(),
            operation_id=new_uuid()))
        _ok(pu.ActivateLoyaltyProgramUseCase(AUTH).execute(
            conn, program_id=programa, actor_user_id=ANA, actor_branch_id=new_uuid(),
            operation_id=new_uuid()))
        cliente = _customer(conn)
        _ok(mu.EnrollLoyaltyMembershipUseCase(AUTH).execute(
            conn, customer_id=cliente, program_id=programa, actor_user_id=ANA,
            actor_branch_id=new_uuid(), operation_id=new_uuid()))
        _ok(bu.ConfigureBirthdayBenefitUseCase(AUTH).execute(
            conn, program_id=programa, actor_user_id=ANA, operation_id=new_uuid(),
            benefit_type=BirthdayBenefitType.POINTS, points_amount=Decimal("200"),
            days_before=2, days_after=2))
        _ok(_set_birthday(conn, cliente, 6, 10))
        assert GrantDueBirthdayBenefitsUseCase().execute(
            conn, today=date(2026, 6, 1)).data["granted"] == 0
        assert GrantDueBirthdayBenefitsUseCase().execute(
            conn, today=date(2026, 6, 9)).data["granted"] == 1
        assert GrantDueBirthdayBenefitsUseCase().execute(
            conn, today=date(2026, 6, 11)).data["granted"] == 0
        assert _points(conn, cliente) == 200


class TestReturnsWithBonuses:
    def test_fixed_bonus_stays_while_the_rest_still_qualifies(self, conn):
        from backend.application.loyalty.use_cases.sale_points_use_cases import (
            RemoveSalePointsUseCase,
            delegated_policy,
        )

        rid = _ok(ru.CreateLoyaltyRuleUseCase(AUTH).execute(
            conn, code="MIN300", name="Bono por compra de 300", rule_type="FIXED_BONUS",
            actor_user_id=ANA, actor_branch_id=new_uuid(), operation_id=new_uuid(),
            form={"points": Decimal("50"), "min_subtotal": Decimal("300")})).entity_id
        _ok(ru.ActivateLoyaltyRuleUseCase(AUTH).execute(
            conn, rule_id=rid, actor_user_id=BETO, actor_branch_id=new_uuid(),
            operation_id=new_uuid()))
        cliente = _customer(conn)
        venta = _sale(conn, cliente, "500")
        assert _points(conn, cliente) == 100   # 50 base + 50 bono

        def devolver(doc, devuelto):
            return _ok(RemoveSalePointsUseCase(delegated_policy(ANA)).execute(
                conn, sale_id=venta, customer_id=cliente, document_id=doc,
                sale_total=Decimal("500"), refunded_total=Decimal(devuelto),
                branch_id=new_uuid(), actor_user_id=ANA, operation_id=new_uuid()))

        devolver("D1", "100")   # quedan 400 ≥ 300: el bono se queda; base 10 menos
        assert _points(conn, cliente) == 90
        devolver("D2", "250")   # devuelto acumulado 250: quedan 250 < 300, se va el bono
        assert _points(conn, cliente) == 100 - 25 - 50   # base: 250/500 de 50
        devolver("D3", "500")   # total: no queda nada de esa compra
        assert _points(conn, cliente) == 0


class TestProductReward:
    def test_confirming_a_product_reward_issues_stock_and_posts_its_cost(self, conn):
        from backend.application.loyalty.integrations.finance_posting import post_loyalty_finance
        from backend.application.loyalty.use_cases import membership_use_cases as mu
        from backend.application.loyalty.use_cases import program_use_cases as pu
        from backend.application.loyalty.use_cases import reward_use_cases as rw
        from backend.domain.loyalty.enums import RewardType
        from tests.integration._pos_ready import stock_product

        sucursal = new_uuid()
        unidad = new_uuid()
        conn.execute("INSERT INTO units_of_measure (id, code, name, dimension, active)"
                     " VALUES (?,?,?,?,1)", (unidad, "PZA", "PZA", "COUNT"))
        producto = new_uuid()
        conn.execute("INSERT INTO products (id, code, name, product_type, base_unit_id,"
                     " lifecycle_status) VALUES (?,?,?,?,?,?)",
                     (producto, "TERMO", "Termo", "SIMPLE", unidad, "ACTIVE"))
        conn.commit()
        stock_product(conn, product_id=producto, branch_id=sucursal, quantity="3")
        import backend.infrastructure.integrations.loyalty_reward_inventory_client as cli
        cli.LoyaltyRewardInventoryClient._unit_cost = lambda self, pid: Decimal("45.50")

        programa = _ok(pu.CreateLoyaltyProgramUseCase(AUTH).execute(
            conn, code="P1", name="Puntos", currency_name="Puntos", actor_user_id=ANA,
            actor_branch_id=new_uuid(), operation_id=new_uuid())).entity_id
        _ok(pu.ApproveLoyaltyProgramUseCase(AUTH).execute(
            conn, program_id=programa, actor_user_id=BETO, actor_branch_id=new_uuid(),
            operation_id=new_uuid()))
        _ok(pu.ActivateLoyaltyProgramUseCase(AUTH).execute(
            conn, program_id=programa, actor_user_id=ANA, actor_branch_id=new_uuid(),
            operation_id=new_uuid()))
        cliente = _customer(conn)
        membresia = _ok(mu.EnrollLoyaltyMembershipUseCase(AUTH).execute(
            conn, customer_id=cliente, program_id=programa, actor_user_id=ANA,
            actor_branch_id=sucursal, operation_id=new_uuid())).entity_id
        _sale(conn, cliente, "5000")
        recompensa = _ok(rw.CreateRewardUseCase(AUTH).execute(
            conn, program_id=programa, code="TERMO", name="Termo", reward_type=RewardType.PRODUCT,
            points_cost=Decimal("300"), actor_user_id=ANA, operation_id=new_uuid(),
            product_code="termo", product_quantity=Decimal("2"))).entity_id
        canje = _ok(rw.RequestRewardRedemptionUseCase(AUTH).execute(
            conn, reward_id=recompensa, membership_id=membresia, actor_user_id=ANA,
            actor_branch_id=sucursal, operation_id=new_uuid())).entity_id
        _ok(rw.ConfirmRewardRedemptionUseCase(AUTH).execute(
            conn, redemption_id=canje, actor_user_id=ANA, actor_branch_id=sucursal,
            operation_id=new_uuid()))

        saldo = conn.execute("SELECT SUM(CAST(quantity AS REAL)) FROM inventory_balances WHERE product_id=?",
                             (producto,)).fetchone()[0]
        assert Decimal(str(saldo)) == Decimal("1")
        entrega = conn.execute("SELECT cost_amount FROM loyalty_reward_deliveries").fetchone()[0]
        assert Decimal(entrega) == Decimal("91.00")
        assert post_loyalty_finance(conn)["failed"] == 0
        costo = conn.execute(
            "SELECT SUM(CAST(l.debit_amount AS TEXT)) FROM journal_lines l JOIN accounts a"
            " ON a.id = l.account_id WHERE a.code='5101'").fetchone()[0]
        assert Decimal(str(costo)) == Decimal("91.00")

    def test_without_stock_the_reward_is_not_delivered(self, conn):
        from backend.application.loyalty.use_cases.reward_use_cases import _deliver_product
        from backend.domain.loyalty.exceptions import LoyaltyDomainError
        from backend.infrastructure.db.repositories.loyalty.rule_repository import (
            LoyaltyRewardProductRepository,
        )

        class _Canje:
            id = new_uuid()
            reward_id = new_uuid()

        LoyaltyRewardProductRepository(conn).link(_Canje.reward_id, new_uuid(), Decimal("1"))
        with pytest.raises(LoyaltyDomainError, match="existencia"):
            _deliver_product(conn, _Canje, new_uuid(), ANA)


class TestCleanBirth:
    """REGLA CERO: la validación de arranque rechaza cualquier columna de llave
    primaria entera. La 297 creó `loyalty_birthday_grants.year INTEGER` y la
    aplicación dejó de abrir (2026-10-03); la 298 la reconstruye."""

    def test_new_tables_have_no_integer_primary_key(self, conn):
        from backend.infrastructure.db.uuid_cutover import find_integer_pks

        nuevas = {"loyalty_birthday_grants", "loyalty_reward_products",
                  "loyalty_reward_deliveries", "customer_birthdays", "loyalty_rules",
                  "loyalty_sale_evaluations", "loyalty_rule_applications",
                  "loyalty_stacking_rules", "loyalty_finance_links",
                  "loyalty_finance_point_credits", "loyalty_finance_point_allocations"}
        assert not (set(find_integer_pks(conn)) & nuevas)

    def test_298_rebuilds_the_integer_year_keeping_rows(self):
        from backend.infrastructure.db.uuid_cutover import find_integer_pks

        c = sqlite3.connect(":memory:")
        c.executescript("""
            CREATE TABLE loyalty_birthday_grants (program_id TEXT NOT NULL,
                customer_id TEXT NOT NULL, year INTEGER NOT NULL, granted_at TEXT NOT NULL,
                PRIMARY KEY (program_id, customer_id, year));
            INSERT INTO loyalty_birthday_grants VALUES ('p', 'c', 2026, '2026-06-09');
            CREATE TABLE gone (id TEXT);
            CREATE VIEW v_broken AS SELECT * FROM gone;
            DROP TABLE gone;
        """)
        m = importlib.import_module("migrations.standalone.298_birthday_grants_text_year")
        m.run(c)
        m.run(c)
        assert find_integer_pks(c) == {}
        assert c.execute("SELECT year FROM loyalty_birthday_grants").fetchall() == [("2026",)]
