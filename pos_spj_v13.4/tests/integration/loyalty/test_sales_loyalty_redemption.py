"""Canje de puntos en el punto de venta, contra el esquema real.

Cubre lo que reemplazó a `core/services/loyalty_service.py`. Las reglas
—mínimo, tope del 50 % del ticket, conversión a pesos— no se inventaron: su
contrato sobrevive en `tests/test_loyalty_redemption_source.py`, y estos tests
las vuelven a fijar sobre la implementación canónica.

Lo que más importa aquí es el SALDO: sale de UN solo libro,
`loyalty_transactions`. Hasta LOY-29 se sumaba también el legacy
`loyalty_ledger`; tenía cero filas y cero escritores en la base real, así que
se retiró (migración 291) y aquí se fija que ya no se lee.
"""
from __future__ import annotations

import sqlite3
from decimal import Decimal

import pytest

from backend.application.loyalty.queries.redemption_preview_query import (
    LoyaltyRedemptionPreviewQuery,
)
from backend.domain.loyalty.policies.redemption_policy import (
    LoyaltyRedemptionPolicy,
    RedemptionSettings,
)
from backend.infrastructure.db.schema.loyalty_schema import create_loyalty_schema
from backend.application.loyalty.authorization import LoyaltyAuthorizationPolicy
from backend.infrastructure.integrations.sales_loyalty_client import SalesLoyaltyClient
from backend.shared.ids import new_uuid
from tests.integration._governed_settings import ensure_governance, set_setting
from backend.domain.settings.exceptions import ConfigurationInvalidValueError


@pytest.fixture
def conn():
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    create_loyalty_schema(c)
    c.executescript(
        """
        CREATE TABLE configuraciones (clave TEXT PRIMARY KEY, valor TEXT);
        """
    )
    c.commit()
    yield c
    c.close()


def _client(conn, **kwargs) -> SalesLoyaltyClient:
    """Cliente con política PERMISIVA EXPLÍCITA.

    Sin ella el canje falla cerrado (§23) — que es lo correcto, y lo prueba
    `test_without_authorization_nothing_is_redeemed`.
    """
    return SalesLoyaltyClient(
        conn, authorization=LoyaltyAuthorizationPolicy.permissive_for_tests(), **kwargs)


def _settings(conn, **valores):
    for clave, valor in valores.items():
        set_setting(conn, clave, valor)


def _canonical_account(conn, customer_id: str, puntos: int = 0) -> str:
    """Cuenta canónica con saldo, por la vía real (ledger, no un campo)."""
    from backend.domain.loyalty.entities.loyalty_account import LoyaltyAccount
    from backend.domain.loyalty.entities.loyalty_transaction import LoyaltyTransaction
    from backend.infrastructure.db.repositories.loyalty.account_repository import (
        LoyaltyAccountRepository,
    )
    from backend.infrastructure.db.repositories.loyalty.transaction_repository import (
        LoyaltyTransactionRepository,
    )

    account = LoyaltyAccount.create(customer_id=customer_id)
    LoyaltyAccountRepository(conn).save(account)
    if puntos:
        LoyaltyTransactionRepository(conn).save(LoyaltyTransaction.earn(
            loyalty_account_id=account.id, points_amount=Decimal(puntos),
            operation_id=new_uuid(), branch_id=new_uuid(), created_by_user_id=new_uuid()))
    conn.commit()
    return account.id


# ── la política, aislada ────────────────────────────────────────────────────
class TestRedemptionPolicy:
    def test_the_percentage_cap_limits_what_can_be_redeemed(self):
        """Subtotal 100, tope 50 %, punto = $0.10 → 500 puntos como máximo.

        Es lo que impide pagar una venta entera con puntos."""
        assert LoyaltyRedemptionPolicy.max_redeemable_points(
            balance=1000, subtotal=Decimal("100"), settings=RedemptionSettings()) == 500

    def test_the_balance_also_limits(self):
        assert LoyaltyRedemptionPolicy.max_redeemable_points(
            balance=120, subtotal=Decimal("100"), settings=RedemptionSettings()) == 120

    def test_below_the_minimum_nothing_can_be_redeemed(self):
        """No es "canjea lo que tengas": es una puerta cerrada."""
        assert LoyaltyRedemptionPolicy.max_redeemable_points(
            balance=50, subtotal=Decimal("200"),
            settings=RedemptionSettings(min_points=100)) == 0

    def test_a_request_above_the_cap_is_trimmed_not_rejected(self):
        """La caja pide y el sistema responde con lo que de verdad aplica."""
        preview = LoyaltyRedemptionPolicy.preview(
            balance=1000, subtotal=Decimal("100"), settings=RedemptionSettings(),
            requested_points=900)
        assert preview.requested_points == 500
        assert preview.discount == Decimal("50.00")

    def test_the_discount_never_exceeds_half_the_ticket(self):
        preview = LoyaltyRedemptionPolicy.preview(
            balance=99999, subtotal=Decimal("240"), settings=RedemptionSettings(),
            requested_points=99999)
        assert preview.discount <= Decimal("240") * Decimal("0.5")

    def test_a_zero_point_value_does_not_grant_infinite_discount(self):
        """Un programa mal configurado no puede regalar la venta."""
        assert LoyaltyRedemptionPolicy.max_redeemable_points(
            balance=1000, subtotal=Decimal("100"),
            settings=RedemptionSettings(point_value=Decimal("0"))) == 0

    def test_a_preview_without_a_request_redeems_nothing(self):
        preview = LoyaltyRedemptionPolicy.preview(
            balance=500, subtotal=Decimal("100"), settings=RedemptionSettings())
        assert preview.requested_points == 0 and preview.discount == Decimal("0")
        assert preview.max_redeemable_points == 500


# ── el saldo, que abarca los dos libros ─────────────────────────────────────
class TestSingleLedgerBalance:
    def test_canonical_points_count(self, conn):
        customer_id = new_uuid()
        _canonical_account(conn, customer_id, puntos=120)
        assert LoyaltyRedemptionPreviewQuery(conn).balance(customer_id) == 120

    def test_another_customers_points_are_not_counted(self, conn):
        mine, other = new_uuid(), new_uuid()
        _canonical_account(conn, other, puntos=900)
        assert LoyaltyRedemptionPreviewQuery(conn).balance(mine) == 0

    def test_the_legacy_ledger_is_not_a_second_source(self, conn):
        """LOY-29: un `loyalty_ledger` que sobreviviera en alguna base no suma.
        Un solo libro de puntos (§11, §73)."""
        customer_id = new_uuid()
        _canonical_account(conn, customer_id, puntos=100)
        conn.executescript(
            "CREATE TABLE loyalty_ledger (id TEXT PRIMARY KEY, cliente_id TEXT, tipo TEXT,"
            " puntos INTEGER);")
        conn.execute("INSERT INTO loyalty_ledger VALUES (?,?,?,?)",
                     (new_uuid(), customer_id, "acumulacion", 500))
        conn.commit()
        assert LoyaltyRedemptionPreviewQuery(conn).balance(customer_id) == 100

    def test_a_customer_without_any_history_has_no_points(self, conn):
        assert LoyaltyRedemptionPreviewQuery(conn).balance(new_uuid()) == 0


# ── ajustes ─────────────────────────────────────────────────────────────────
class TestSettings:
    def test_configured_values_are_used(self, conn):
        _settings(conn, **{"loyalty.point_value": "0.25", "loyalty.min_points_to_redeem": "10",
                           "loyalty.max_redeem_fraction": "0.3"})
        settings = LoyaltyRedemptionPreviewQuery(conn).settings()
        assert settings.point_value == Decimal("0.25")
        assert settings.min_points == 10
        assert settings.max_percent == Decimal("0.3")

    def test_a_corrupt_value_cannot_be_stored_and_the_sale_keeps_the_default(self, conn):
        """Antes un valor corrupto se guardaba y el lector caía al de fábrica.
        Ahora el gobierno lo rechaza al guardarlo: nunca llega al cobro."""
        with pytest.raises(ConfigurationInvalidValueError):
            _settings(conn, **{"loyalty.point_value": "no-es-un-numero"})
        assert LoyaltyRedemptionPreviewQuery(conn).settings().point_value == Decimal("0.10")


# ── el cliente que usa Ventas ───────────────────────────────────────────────
class TestSalesLoyaltyClient:
    def test_preview_keeps_the_shape_its_consumers_read(self, conn):
        customer_id = new_uuid()
        _canonical_account(conn, customer_id, puntos=1000)
        preview = SalesLoyaltyClient(conn).preview_redemption(
            customer_id=customer_id, subtotal=Decimal("100"))

        for clave in ("enabled", "puntos_disponibles", "puntos_maximos_canjeables",
                      "descuento_maximo", "puntos_solicitados", "descuento",
                      "total_original", "total_con_descuento"):
            assert clave in preview, clave
        assert preview["enabled"] is True
        assert preview["puntos_maximos_canjeables"] == 500

    def test_a_sale_without_a_customer_is_not_an_error(self, conn):
        """Vender a público general es lo normal, no una excepción."""
        preview = SalesLoyaltyClient(conn).preview_redemption(
            customer_id="", subtotal=Decimal("100"))
        assert preview["enabled"] is False
        assert preview["descuento"] == 0.0

    def test_peek_never_fabricates_points_earned(self, conn):
        """Un cero se leería en el ticket como "esta compra no generó puntos"."""
        customer_id = new_uuid()
        _canonical_account(conn, customer_id, puntos=40)
        resumen = SalesLoyaltyClient(conn).peek_loyalty_summary(customer_id=customer_id)
        assert resumen.points_balance == 40
        assert resumen.points_earned is None

    def test_preview_has_no_side_effects(self, conn):
        """La caja llama a esto mientras el cajero teclea."""
        customer_id = new_uuid()
        _canonical_account(conn, customer_id, puntos=500)
        antes = conn.execute("SELECT COUNT(*) FROM loyalty_transactions").fetchone()[0]

        for _ in range(3):
            SalesLoyaltyClient(conn).preview_redemption(
                customer_id=customer_id, subtotal=Decimal("100"))

        assert conn.execute("SELECT COUNT(*) FROM loyalty_transactions").fetchone()[0] == antes

    def test_redeem_deducts_from_the_balance(self, conn):
        customer_id, cashier = new_uuid(), new_uuid()
        _canonical_account(conn, customer_id, puntos=500)
        query = LoyaltyRedemptionPreviewQuery(conn)

        resultado = _client(conn, actor_branch_id=new_uuid()).redeem(
            customer_id=customer_id, sale_id=new_uuid(), subtotal=Decimal("100"),
            points=200, actor_user_id=cashier)

        assert resultado["approved"] is True
        assert resultado["points_redeemed"] == 200
        assert resultado["discount_amount"] == Decimal("20.00")
        assert query.balance(customer_id) == 300

    def test_redeem_trims_to_the_cap_instead_of_trusting_the_caller(self, conn):
        """Es el tope real: usar el número crudo del llamador lo saltaría.

        Se comprueba el SALDO, no sólo lo que devuelve el método. Mirar
        únicamente el diccionario no prueba nada: si se descontara la cantidad
        cruda, el valor devuelto seguiría siendo el recortado y los dos números
        divergirían en silencio — se informaría de 500 puntos habiendo quitado
        5000. (Verificado con una mutación: sin esta comprobación del saldo, el
        cambio pasaba las 24 pruebas.)
        """
        customer_id, cashier = new_uuid(), new_uuid()
        _canonical_account(conn, customer_id, puntos=5000)

        resultado = _client(conn, actor_branch_id=new_uuid()).redeem(
            customer_id=customer_id, sale_id=new_uuid(), subtotal=Decimal("100"),
            points=5000, actor_user_id=cashier)

        assert resultado["points_redeemed"] == 500        # 50 % de $100 a $0.10
        assert resultado["discount_amount"] == Decimal("50.00")
        # Lo que de verdad se quitó del libro.
        assert LoyaltyRedemptionPreviewQuery(conn).balance(customer_id) == 4500

    def test_what_is_reported_is_what_is_deducted(self, conn):
        """Informar de una cantidad y descontar otra es peor que rechazar."""
        customer_id, cashier = new_uuid(), new_uuid()
        _canonical_account(conn, customer_id, puntos=1000)
        antes = LoyaltyRedemptionPreviewQuery(conn).balance(customer_id)

        resultado = _client(conn, actor_branch_id=new_uuid()).redeem(
            customer_id=customer_id, sale_id=new_uuid(), subtotal=Decimal("60"),
            points=900, actor_user_id=cashier)

        despues = LoyaltyRedemptionPreviewQuery(conn).balance(customer_id)
        assert antes - despues == resultado["points_redeemed"]

    def test_a_customer_without_a_loyalty_account_is_rejected_not_crashed(self, conn):
        resultado = _client(conn).redeem(
            customer_id=new_uuid(), sale_id=new_uuid(), subtotal=Decimal("100"),
            points=10, actor_user_id=new_uuid())
        assert resultado["approved"] is False
        assert resultado["points_redeemed"] == 0

    def test_redeeming_the_same_sale_twice_does_not_deduct_twice(self, conn):
        """El `operation_id` se deriva de la venta."""
        customer_id, cashier, sale_id = new_uuid(), new_uuid(), new_uuid()
        _canonical_account(conn, customer_id, puntos=500)
        client = _client(conn, actor_branch_id=new_uuid())

        client.redeem(customer_id=customer_id, sale_id=sale_id,
                      subtotal=Decimal("100"), points=100, actor_user_id=cashier)
        client.redeem(customer_id=customer_id, sale_id=sale_id,
                      subtotal=Decimal("100"), points=100, actor_user_id=cashier)

        assert LoyaltyRedemptionPreviewQuery(conn).balance(customer_id) == 400


    def test_without_authorization_nothing_is_redeemed(self, conn):
        """§23: un cliente sin política inyectada no concede nada.

        Vale la pena fijarlo: el caso de uso trae una política PERMISIVA por
        omisión, así que construirlo sin argumentos —lo natural— habría
        concedido cualquier permiso de fidelidad en producción.
        """
        customer_id, cashier = new_uuid(), new_uuid()
        _canonical_account(conn, customer_id, puntos=500)

        resultado = SalesLoyaltyClient(conn, actor_branch_id=new_uuid()).redeem(
            customer_id=customer_id, sale_id=new_uuid(), subtotal=Decimal("100"),
            points=100, actor_user_id=cashier)

        assert resultado["approved"] is False
        assert LoyaltyRedemptionPreviewQuery(conn).balance(customer_id) == 500
