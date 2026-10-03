"""Fidelidad → Finanzas (2026-10-03): puntos, vales, cupones y premios de
sorteo llegan a contabilidad, contra el esquema real y el catálogo sembrado.

Decisión del usuario: "contabiliza los puntos, cupones, vales, boletos y
cualquier programa de fidelidad". Antes NINGÚN movimiento de Fidelidad
llegaba a contabilidad. Lo que se fija aquí:

* Toda póliza cuadra (debe = haber) y el saldo de cada pasivo coincide con lo
  que el cliente aún tiene.
* Puntos: acumular reconoce el pasivo al valor del punto; canjear en una venta
  acredita el DESCUENTO que la venta cargó (no un segundo ingreso); caducar va a
  breakage; un apartado no asienta hasta confirmarse; liberar no asienta nada;
  el reverso de un canje lo deshace con espejo.
* Vales: emisión, canje parcial, vale cancelado con saldo.
* Cupones: el canje en venta se reclasifica a contra-ingreso por cupones; el
  financiado por proveedor queda por cobrar.
* Sorteos: provisión al activar, uso al entregar, liberación al resolver.
* Idempotencia: correr el puente dos veces no duplica nada.
"""

from __future__ import annotations

import sqlite3
from datetime import date
from decimal import Decimal

import pytest

from backend.application.loyalty.authorization import LoyaltyAuthorizationPolicy
from backend.application.loyalty.integrations.finance_posting import (
    LoyaltyFinancePostingService,
)
from backend.shared.ids import new_uuid

TODAY = date.today()


@pytest.fixture(scope="module")
def template_db():
    import migrations.m000_base_schema as base
    from backend.application.services.finance.finance_bootstrap import bootstrap_finance
    from backend.infrastructure.db.schema.commercial_instruments_schema import (
        create_commercial_instruments_schema,
    )
    from backend.infrastructure.db.schema.finance_schema import create_finance_schema
    from backend.infrastructure.db.schema.loyalty_finance_schema import (
        create_loyalty_finance_tables,
    )
    from backend.infrastructure.db.schema.loyalty_schema import create_loyalty_schema
    from backend.infrastructure.db.schema.sweepstakes_schema import create_sweepstakes_schema

    c = sqlite3.connect(":memory:")
    base.up(c)
    create_finance_schema(c)
    for crear in (create_loyalty_schema, create_commercial_instruments_schema,
                  create_sweepstakes_schema, create_loyalty_finance_tables):
        crear(c)
    c.commit()
    bootstrap_finance(c, today=TODAY)
    c.execute("INSERT OR REPLACE INTO configuraciones (clave, valor) VALUES"
              " ('loyalty_valor_estrella', '0.10')")
    c.commit()
    yield c
    c.close()


@pytest.fixture
def conn(template_db):
    c = sqlite3.connect(":memory:")
    template_db.backup(c)
    c.row_factory = sqlite3.Row
    yield c
    c.close()


AUTH = LoyaltyAuthorizationPolicy.permissive_for_tests()
USER = new_uuid()
BRANCH = new_uuid()


def _run(conn):
    return LoyaltyFinancePostingService(conn).run()


def _balance(conn, code: str) -> Decimal:
    """Saldo deudor (debe - haber) de una cuenta en las pólizas."""
    total = Decimal("0")
    for row in conn.execute(
            "SELECT l.debit_amount, l.credit_amount FROM journal_lines l"
            " JOIN accounts a ON a.id = l.account_id WHERE a.code=?", (code,)):
        total += Decimal(row["debit_amount"]) - Decimal(row["credit_amount"])
    return total


def _entries_balance(conn) -> None:
    for entry in conn.execute("SELECT id FROM journal_entries").fetchall():
        debe = haber = Decimal("0")
        for row in conn.execute("SELECT debit_amount, credit_amount FROM journal_lines"
                                " WHERE journal_entry_id=?", (entry["id"],)):
            debe += Decimal(row["debit_amount"])
            haber += Decimal(row["credit_amount"])
        assert debe == haber, f"póliza {entry['id']} descuadrada: {debe} != {haber}"


def _account(conn, customer_id: str | None = None) -> str:
    from backend.domain.loyalty.entities.loyalty_account import LoyaltyAccount
    from backend.infrastructure.db.repositories.loyalty.account_repository import (
        LoyaltyAccountRepository,
    )

    cuenta = LoyaltyAccount.create(customer_id or new_uuid())
    LoyaltyAccountRepository(conn).save(cuenta)
    conn.commit()
    return cuenta.id


def _ok(result):
    assert result.success, result.message
    return result


def _accrue(conn, account_id: str, points: int, **kw):
    from backend.application.loyalty.use_cases.ledger_use_cases import AccrueLoyaltyPointsUseCase

    return _ok(AccrueLoyaltyPointsUseCase(AUTH).execute(
        conn, loyalty_account_id=account_id, points_amount=Decimal(points),
        operation_id=new_uuid(), actor_user_id=USER, actor_branch_id=BRANCH,
        source_module="sales", reason_code="SALE", source_document_id=new_uuid(), **kw))


def _redeem(conn, account_id: str, points: int, sale_id: str | None = None):
    from backend.application.loyalty.use_cases.ledger_use_cases import RedeemLoyaltyPointsUseCase

    return _ok(RedeemLoyaltyPointsUseCase(AUTH).execute(
        conn, loyalty_account_id=account_id, points_amount=Decimal(points),
        operation_id=new_uuid(), actor_user_id=USER, actor_branch_id=BRANCH,
        source_module="sales", sale_id=sale_id))


class TestPoints:
    def test_accrual_recognizes_liability_at_point_value(self, conn):
        cuenta = _account(conn)
        _accrue(conn, cuenta, 100)
        resumen = _run(conn)
        assert resumen.posted == 1 and resumen.failed == 0
        assert _balance(conn, "2130") == Decimal("-10.00")   # pasivo (haber)
        assert _balance(conn, "4202") == Decimal("10.00")    # contra-ingreso
        _entries_balance(conn)

    def test_redemption_in_a_sale_credits_the_sale_discount(self, conn):
        cuenta = _account(conn)
        _accrue(conn, cuenta, 100)
        _redeem(conn, cuenta, 40, sale_id=new_uuid())
        _run(conn)
        assert _balance(conn, "2130") == Decimal("-6.00")
        # La venta cargó 4.00 de descuento por esos puntos; el canje lo abona.
        assert _balance(conn, "4201") == Decimal("-4.00")
        assert _balance(conn, "4101") == Decimal("0")
        _entries_balance(conn)

    def test_redemption_outside_a_sale_is_revenue(self, conn):
        cuenta = _account(conn)
        _accrue(conn, cuenta, 100)
        _redeem(conn, cuenta, 30)
        _run(conn)
        assert _balance(conn, "4101") == Decimal("-3.00")
        assert _balance(conn, "2130") == Decimal("-7.00")

    def test_fifo_values_each_point_at_its_own_recognition(self, conn):
        cuenta = _account(conn)
        _accrue(conn, cuenta, 100)                      # a 0.10
        LoyaltyFinancePostingService(conn, point_value=Decimal("0.10")).run()
        _accrue(conn, cuenta, 100)                      # a 0.20
        LoyaltyFinancePostingService(conn, point_value=Decimal("0.20")).run()
        _redeem(conn, cuenta, 150)                      # 100 × 0.10 + 50 × 0.20
        LoyaltyFinancePostingService(conn, point_value=Decimal("0.20")).run()
        assert _balance(conn, "4101") == Decimal("-20.00")
        assert _balance(conn, "2130") == Decimal("-10.00")  # 50 × 0.20 que quedan

    def test_expiry_releases_only_what_remains_into_breakage(self, conn):
        from backend.application.loyalty.use_cases.ledger_use_cases import (
            ExpireLoyaltyPointsUseCase,
        )

        cuenta = _account(conn)
        _accrue(conn, cuenta, 100, expires_at="2020-01-01T00:00:00+00:00")
        _redeem(conn, cuenta, 30)
        _ok(ExpireLoyaltyPointsUseCase(AUTH).execute(
            conn, before_iso="2021-01-01T00:00:00+00:00", operation_id_prefix=new_uuid()))
        _run(conn)
        assert _balance(conn, "4120") == Decimal("-7.00")   # 70 puntos caducos
        assert _balance(conn, "2130") == Decimal("0")
        _entries_balance(conn)

    def test_reservation_posts_only_when_confirmed_and_release_posts_nothing(self, conn):
        from backend.application.loyalty.use_cases.ledger_use_cases import (
            ConfirmReservedLoyaltyPointsUseCase,
            ReleaseLoyaltyPointsUseCase,
            ReserveLoyaltyPointsUseCase,
        )

        cuenta = _account(conn)
        _accrue(conn, cuenta, 100)
        reserva = _ok(ReserveLoyaltyPointsUseCase(AUTH).execute(
            conn, loyalty_account_id=cuenta, points_amount=Decimal(50),
            operation_id=new_uuid(), actor_user_id=USER, actor_branch_id=BRANCH))
        resumen = _run(conn)
        assert resumen.held == 1
        assert _balance(conn, "2130") == Decimal("-10.00")   # nada canjeado aún
        _ok(ConfirmReservedLoyaltyPointsUseCase(AUTH).execute(
            conn, transaction_id=reserva.entity_id, actor_user_id=USER,
            actor_branch_id=BRANCH, operation_id=new_uuid()))
        _run(conn)
        assert _balance(conn, "2130") == Decimal("-5.00")

        otra = _ok(ReserveLoyaltyPointsUseCase(AUTH).execute(
            conn, loyalty_account_id=cuenta, points_amount=Decimal(20),
            operation_id=new_uuid(), actor_user_id=USER, actor_branch_id=BRANCH))
        _run(conn)
        _ok(ReleaseLoyaltyPointsUseCase(AUTH).execute(
            conn, transaction_id=otra.entity_id, actor_user_id=USER,
            actor_branch_id=BRANCH, operation_id=new_uuid()))
        _run(conn)
        assert _balance(conn, "2130") == Decimal("-5.00")
        # Los 20 liberados vuelven a estar disponibles para el siguiente canje.
        _redeem(conn, cuenta, 50)
        resumen = _run(conn)
        assert resumen.warnings == []
        assert _balance(conn, "2130") == Decimal("0")

    def test_reversing_a_sale_redemption_mirrors_it(self, conn):
        from backend.application.loyalty.use_cases.ledger_use_cases import (
            ReverseLoyaltyTransactionUseCase,
        )

        cuenta = _account(conn)
        _accrue(conn, cuenta, 100)
        canje = _redeem(conn, cuenta, 40, sale_id=new_uuid())
        _run(conn)
        _ok(ReverseLoyaltyTransactionUseCase(AUTH).execute(
            conn, transaction_id=canje.entity_id, reason_code="SALE_CANCELLED",
            actor_user_id=USER, actor_branch_id=BRANCH, operation_id=new_uuid()))
        _run(conn)
        assert _balance(conn, "2130") == Decimal("-10.00")
        assert _balance(conn, "4201") == Decimal("0")
        _entries_balance(conn)

    def test_reversing_an_accrual_withdraws_the_recognition(self, conn):
        from backend.application.loyalty.use_cases.ledger_use_cases import (
            ReverseLoyaltyTransactionUseCase,
        )

        cuenta = _account(conn)
        acumulado = _accrue(conn, cuenta, 100)
        _run(conn)
        _ok(ReverseLoyaltyTransactionUseCase(AUTH).execute(
            conn, transaction_id=acumulado.entity_id, reason_code="ERROR",
            actor_user_id=USER, actor_branch_id=BRANCH, operation_id=new_uuid()))
        _run(conn)
        assert _balance(conn, "2130") == Decimal("0")
        assert _balance(conn, "4202") == Decimal("0")

    def test_bonus_without_event_is_still_recognized(self, conn):
        """Los bonos (cumpleaños, retos, referidos) no emitían evento: el puente
        lee el libro, así que también se reconocen."""
        from backend.domain.loyalty.entities.loyalty_transaction import LoyaltyTransaction
        from backend.infrastructure.db.repositories.loyalty.transaction_repository import (
            LoyaltyTransactionRepository,
        )

        cuenta = _account(conn)
        LoyaltyTransactionRepository(conn).save(LoyaltyTransaction.bonus(
            loyalty_account_id=cuenta, points_amount=Decimal(50), operation_id=new_uuid(),
            reason_code="BIRTHDAY"))
        conn.commit()
        _run(conn)
        assert _balance(conn, "2130") == Decimal("-5.00")

    def test_running_twice_posts_nothing_new(self, conn):
        cuenta = _account(conn)
        _accrue(conn, cuenta, 100)
        _redeem(conn, cuenta, 10, sale_id=new_uuid())
        _run(conn)
        polizas = conn.execute("SELECT COUNT(*) FROM journal_entries").fetchone()[0]
        segundo = _run(conn)
        assert segundo.posted == 0
        assert conn.execute("SELECT COUNT(*) FROM journal_entries").fetchone()[0] == polizas

    def test_without_profile_it_fails_visibly_and_retries(self, conn):
        conn.execute("UPDATE posting_profiles SET active=0 WHERE profile_key='LOYALTY_POINTS'")
        conn.commit()
        cuenta = _account(conn)
        _accrue(conn, cuenta, 100)
        resumen = _run(conn)
        assert resumen.failed == 1
        fila = conn.execute("SELECT status, detail FROM loyalty_finance_links").fetchone()
        assert fila["status"] == "FAILED" and "perfil" in fila["detail"]
        conn.execute("UPDATE posting_profiles SET active=1 WHERE profile_key='LOYALTY_POINTS'")
        conn.commit()
        assert _run(conn).posted == 1
        assert _balance(conn, "2130") == Decimal("-10.00")


class TestVouchersAndCoupons:
    def _voucher(self, conn, amount: str, voucher_type="REFUND_VOUCHER"):
        from backend.application.commercial_instruments.use_cases import voucher_use_cases as v
        from backend.domain.commercial_instruments.enums import VoucherType

        definicion = _ok(v.CreateVoucherDefinitionUseCase(AUTH).execute(
            conn, code=f"VD-{new_uuid()[-6:]}", name="Vale", voucher_type=VoucherType(voucher_type),
            actor_user_id=USER, operation_id=new_uuid()))
        return _ok(v.IssueVoucherInstanceUseCase(AUTH).execute(
            conn, definition_id=definicion.entity_id, code=f"VAL-{new_uuid()[-6:]}",
            amount=Decimal(amount), actor_user_id=USER, actor_branch_id=BRANCH,
            operation_id=new_uuid())).entity_id

    def test_voucher_issue_and_partial_redemption(self, conn):
        from backend.application.commercial_instruments.use_cases import voucher_use_cases as v

        vale = self._voucher(conn, "200")
        reserva = _ok(v.ReserveVoucherAmountUseCase(AUTH).execute(
            conn, voucher_instance_id=vale, amount=Decimal("80"), sale_id=new_uuid(),
            actor_branch_id=BRANCH, operation_id=new_uuid()))
        resumen = _run(conn)
        assert resumen.held == 1
        assert _balance(conn, "2132") == Decimal("-200.00")
        _ok(v.ConfirmVoucherRedemptionUseCase(AUTH).execute(
            conn, reservation_transaction_id=reserva.entity_id, redeemed_by_user_id=USER,
            actor_branch_id=BRANCH, operation_id=new_uuid()))
        _run(conn)
        assert _balance(conn, "2132") == Decimal("-120.00")
        assert _balance(conn, "4101") == Decimal("-80.00")
        _entries_balance(conn)

    def test_prepaid_voucher_is_not_recognized_without_a_collection(self, conn):
        """Un vale prepagado exigiría un cobro que el sistema no registra: sin
        perfil queda FAILED a la vista, nunca un cargo a caja inventado."""
        self._voucher(conn, "100", "PREPAID_VOUCHER")
        resumen = _run(conn)
        assert resumen.failed == 1
        assert _balance(conn, "1102") == Decimal("0")

    def test_coupon_in_a_sale_is_reclassified(self, conn):
        from backend.application.commercial_instruments.use_cases import coupon_use_cases as cu
        from backend.domain.commercial_instruments.enums import CommercialBenefitType, CouponType

        for tipo, cuenta in (("PERSONALIZED", "4203"), ("SUPPLIER_FUNDED", "1135")):
            definicion = _ok(cu.CreateCouponDefinitionUseCase(AUTH).execute(
                conn, code=f"CD-{new_uuid()[-6:]}", name="Cupón", coupon_type=CouponType(tipo),
                benefit_type=CommercialBenefitType.FIXED_AMOUNT, benefit_value=Decimal("25"),
                actor_user_id=USER, operation_id=new_uuid()))
            cupon = _ok(cu.IssueCouponInstanceUseCase(AUTH).execute(
                conn, definition_id=definicion.entity_id, code=f"CUP-{new_uuid()[-6:]}",
                actor_user_id=USER, actor_branch_id=BRANCH, operation_id=new_uuid()))
            codigo = conn.execute("SELECT code FROM coupon_instances WHERE id=?",
                                  (cupon.entity_id,)).fetchone()[0]
            _ok(cu.ValidateAndReserveCouponUseCase(AUTH).execute(
                conn, code=codigo, sale_id=new_uuid(), actor_user_id=USER,
                actor_branch_id=BRANCH, operation_id=new_uuid()))
            _ok(cu.ConfirmCouponRedemptionUseCase(AUTH).execute(
                conn, coupon_instance_id=cupon.entity_id, amount_applied=Decimal("25"),
                redeemed_by_user_id=USER, actor_branch_id=BRANCH, operation_id=new_uuid()))
            _run(conn)
            assert _balance(conn, cuenta) == Decimal("25.00")
        assert _balance(conn, "4201") == Decimal("-50.00")
        _entries_balance(conn)


class TestSweepstakes:
    def _campaign(self, conn, status="ACTIVE", cost="1500", quantity=2):
        campana, premio = new_uuid(), new_uuid()
        ahora = "2026-10-03T12:00:00+00:00"
        conn.execute("INSERT INTO sweepstakes_campaigns (id, code, name, status,"
                     " created_by_user_id, created_at, updated_at) VALUES (?,?,?,?,?,?,?)",
                     (campana, f"S-{campana[-6:]}", "Gran sorteo", status, USER, ahora, ahora))
        conn.execute("INSERT INTO sweepstakes_prizes (id, campaign_id, name, quantity,"
                     " estimated_cost, created_at) VALUES (?,?,?,?,?,?)",
                     (premio, campana, "Pantalla", quantity, cost, ahora))
        conn.commit()
        return campana, premio

    def _winner(self, conn, campana, premio, status="PRIZE_DELIVERED"):
        ganador = new_uuid()
        conn.execute("INSERT INTO sweepstakes_winners (id, draw_id, campaign_id, ticket_id,"
                     " customer_id, prize_id, status, selected_at, delivered_at)"
                     " VALUES (?,?,?,?,?,?,?,?,?)",
                     (ganador, new_uuid(), campana, new_uuid(), new_uuid(), premio, status,
                      "2026-10-03T12:00:00+00:00", "2026-10-03T13:00:00+00:00"))
        conn.commit()
        return ganador

    def test_prize_provision_use_and_release(self, conn):
        campana, premio = self._campaign(conn)
        _run(conn)
        assert _balance(conn, "2136") == Decimal("-3000.00")
        assert _balance(conn, "6110") == Decimal("3000.00")
        self._winner(conn, campana, premio)
        _run(conn)
        assert _balance(conn, "2136") == Decimal("-1500.00")
        conn.execute("UPDATE sweepstakes_campaigns SET status='DRAWN' WHERE id=?", (campana,))
        conn.commit()
        _run(conn)
        assert _balance(conn, "2136") == Decimal("0")
        assert _balance(conn, "6110") == Decimal("0")   # el costo real lo asienta su compra
        _entries_balance(conn)

    def test_draft_campaign_is_not_provisioned_and_pending_winner_blocks_release(self, conn):
        self._campaign(conn, status="DRAFT")
        _run(conn)
        assert _balance(conn, "2136") == Decimal("0")
        campana, premio = self._campaign(conn, status="DRAWN", quantity=1)
        self._winner(conn, campana, premio, status="VALIDATED")
        _run(conn)
        assert _balance(conn, "2136") == Decimal("-1500.00")   # aún por entregar

    def test_existing_catalog_gets_the_provision_account(self, conn):
        from backend.application.services.finance.finance_bootstrap import (
            ensure_finance_catalog_additions,
        )

        conn.execute("DELETE FROM posting_profiles WHERE profile_key='SWEEPSTAKES_PRIZE'")
        conn.commit()
        assert ensure_finance_catalog_additions(conn) is True
        assert conn.execute("SELECT COUNT(*) FROM posting_profiles"
                            " WHERE profile_key='SWEEPSTAKES_PRIZE'").fetchone()[0] == 1
        assert ensure_finance_catalog_additions(conn) is True
        assert conn.execute("SELECT COUNT(*) FROM posting_profiles"
                            " WHERE profile_key='SWEEPSTAKES_PRIZE'").fetchone()[0] == 1


class TestMigration294:
    def test_rebuilds_obligations_keeping_rows_and_survives_broken_legacy_view(self):
        import importlib

        from backend.application.services.finance.finance_bootstrap import bootstrap_finance
        from backend.infrastructure.db.schema.finance_schema import create_finance_schema

        c = sqlite3.connect(":memory:")
        create_finance_schema(c)
        # El CHECK de antes de la 294 y una fila existente.
        c.executescript("""
            DROP TABLE commercial_obligations;
            CREATE TABLE commercial_obligations (
                id TEXT NOT NULL PRIMARY KEY,
                instrument_type TEXT NOT NULL CHECK (instrument_type IN (
                    'LOYALTY_POINTS','PROMOTIONAL_COUPON','DISCOUNT_COUPON','REFUND_VOUCHER',
                    'STORE_CREDIT','GIFT_CARD','PREPAID_VOUCHER','PROMOTIONAL_BALANCE',
                    'CUSTOMER_WALLET','THIRD_PARTY_VOUCHER')),
                source_module TEXT NOT NULL, source_instrument_id TEXT NOT NULL,
                recognition_basis TEXT NOT NULL, customer_id TEXT, branch_id TEXT,
                currency_code TEXT NOT NULL DEFAULT 'MXN', original_amount TEXT NOT NULL,
                recognized_amount TEXT NOT NULL, redeemed_amount TEXT NOT NULL DEFAULT '0.00',
                released_amount TEXT NOT NULL DEFAULT '0.00',
                status TEXT NOT NULL DEFAULT 'OPEN', issued_at TEXT, expires_at TEXT,
                operation_id TEXT NOT NULL UNIQUE, created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                UNIQUE (instrument_type, source_module, source_instrument_id));
            INSERT INTO commercial_obligations (id, instrument_type, source_module,
                source_instrument_id, recognition_basis, original_amount, recognized_amount,
                operation_id, created_at, updated_at)
            VALUES ('o1', 'LOYALTY_POINTS', 'loyalty', 't1', 'LIABILITY', '5.00', '5.00',
                    'op1', 'x', 'x');
            CREATE TABLE gone (id TEXT);
            CREATE VIEW v_broken AS SELECT * FROM gone;
            DROP TABLE gone;
        """)
        # Catálogo sembrado ANTES de la 294: sin la cuenta 2136 ni su perfil.
        bootstrap_finance(c, today=TODAY)
        c.execute("DELETE FROM posting_profiles WHERE profile_key='SWEEPSTAKES_PRIZE'")
        c.commit()
        m = importlib.import_module("migrations.standalone.294_loyalty_finance_bridge")
        m.run(c)
        m.run(c)   # idempotente
        sql = c.execute("SELECT sql FROM sqlite_master WHERE name='commercial_obligations'"
                        ).fetchone()[0]
        assert "SWEEPSTAKES_PRIZE" in sql
        assert c.execute("SELECT source_instrument_id FROM commercial_obligations").fetchall() == [("t1",)]
        assert c.execute("SELECT COUNT(*) FROM posting_profiles"
                         " WHERE profile_key='SWEEPSTAKES_PRIZE'").fetchone()[0] == 1
        assert c.execute("SELECT 1 FROM sqlite_master WHERE name='loyalty_finance_links'").fetchone()
