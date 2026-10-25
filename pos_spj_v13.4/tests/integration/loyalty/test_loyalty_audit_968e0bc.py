"""Auditoría de Fidelidad 968e0bc (2026-10-22): canje atómico, snapshot del
valor del punto, corrección manual con doble control, alcance de consultas,
base elegible única y protección de margen."""

from __future__ import annotations

from decimal import Decimal

import pytest

from backend.application.sales.use_cases.cart_use_cases import (
    AddSaleLineUseCase,
    AssignCustomerToSaleUseCase,
    StartSaleUseCase,
)
from backend.infrastructure.db.repositories.sales.sale_repository import SaleRepository
from backend.shared.ids import new_uuid
from tests.integration._governed_settings import set_setting
from tests.unit.test_sales_checkout import (  # noqa: F401 - fixture reutilizado
    _allow_all,
    _award_points,
    _create_customer,
    _redeem,
    loyalty_conn,
)


def _sale_with_points(conn, *, points=200, price="500.00"):
    branch, cashier = new_uuid(), new_uuid()
    sale_id = StartSaleUseCase(_allow_all()).execute(
        conn, branch_id=branch, cashier_user_id=cashier, operation_id=new_uuid(),
        actor_user_id=cashier).entity_id
    AddSaleLineUseCase(_allow_all()).execute(
        conn, sale_id=sale_id, product_id=new_uuid(), quantity=Decimal("1"),
        unit_price=Decimal(price), actor_user_id=cashier, operation_id=new_uuid())
    customer_id = _create_customer(conn)
    AssignCustomerToSaleUseCase(_allow_all()).execute(
        conn, sale_id=sale_id, customer_id=customer_id, actor_user_id=cashier,
        operation_id=new_uuid())
    _award_points(conn, customer_id=customer_id, points=points)
    return sale_id, cashier


def _redeems(conn) -> list[tuple]:
    return conn.execute("SELECT points_amount, point_value, monetary_value, sale_id"
                        " FROM loyalty_transactions WHERE transaction_type='REDEEM'").fetchall()


# ── FID-01: el canje y la venta son UNA transacción ─────────────────────────
def test_points_come_back_if_saving_the_sale_fails(loyalty_conn, monkeypatch):
    sale_id, cashier = _sale_with_points(loyalty_conn)
    _with_costs(monkeypatch, {_product_of(loyalty_conn, sale_id): "100"})

    def falla(self, sale):
        raise RuntimeError("disco lleno")

    monkeypatch.setattr(SaleRepository, "save", falla)
    with pytest.raises(RuntimeError, match="disco lleno"):
        _redeem().execute(loyalty_conn, sale_id=sale_id, points=100, actor_user_id=cashier,
                          operation_id=new_uuid())
    monkeypatch.undo()
    _with_costs(monkeypatch, {_product_of(loyalty_conn, sale_id): "100"})
    assert _redeems(loyalty_conn) == []                       # el débito se deshizo
    venta = SaleRepository(loyalty_conn).get(sale_id)
    assert venta.loyalty_redeemed_amount == Decimal("0")
    # y se puede volver a canjear normalmente
    ok = _redeem().execute(loyalty_conn, sale_id=sale_id, points=100, actor_user_id=cashier,
                           operation_id=new_uuid())
    assert ok.success and len(_redeems(loyalty_conn)) == 1


# ── FID-02: un reintento devuelve EXACTAMENTE lo aceptado ───────────────────
def test_retry_after_a_point_value_change_keeps_the_original_discount(loyalty_conn,
                                                                      monkeypatch):
    set_setting(loyalty_conn, "loyalty.point_value", "0.10")
    sale_id, cashier = _sale_with_points(loyalty_conn)
    _with_costs(monkeypatch, {_product_of(loyalty_conn, sale_id): "100"})
    primero = _redeem().execute(loyalty_conn, sale_id=sale_id, points=20,
                                actor_user_id=cashier, operation_id=new_uuid())
    assert primero.success
    descuento = SaleRepository(loyalty_conn).get(sale_id).loyalty_redeemed_amount
    assert descuento == Decimal("2.00")
    set_setting(loyalty_conn, "loyalty.point_value", "0.20")   # reconfiguración
    segundo = _redeem().execute(loyalty_conn, sale_id=sale_id, points=20,
                                actor_user_id=cashier, operation_id=new_uuid())
    assert segundo.success
    assert SaleRepository(loyalty_conn).get(sale_id).loyalty_redeemed_amount == descuento
    (fila,) = _redeems(loyalty_conn)                           # un solo débito
    assert Decimal(fila["point_value"]) == Decimal("0.10")
    assert Decimal(fila["monetary_value"]) == Decimal("2.00")


# ── FID-05: dar puntos a mano es una corrección con doble control ───────────
def _account(conn):
    from backend.domain.loyalty.entities.loyalty_account import LoyaltyAccount
    from backend.infrastructure.db.repositories.loyalty.account_repository import (
        LoyaltyAccountRepository,
    )
    cuenta = LoyaltyAccount.create(customer_id=new_uuid())
    LoyaltyAccountRepository(conn).save(cuenta)
    conn.commit()
    return cuenta.id


def _permissive():
    from backend.application.loyalty.authorization import LoyaltyAuthorizationPolicy
    return LoyaltyAuthorizationPolicy.permissive_for_tests()


def test_manual_credit_without_document_is_refused(loyalty_conn):
    from backend.application.loyalty.use_cases.ledger_use_cases import (
        AccrueLoyaltyPointsUseCase,
    )
    cuenta = _account(loyalty_conn)
    for origen, documento in (("fidelidad_ui", "X-1"), ("campaign", None)):
        r = AccrueLoyaltyPointsUseCase(_permissive()).execute(
            loyalty_conn, loyalty_account_id=cuenta, points_amount=Decimal("50"),
            operation_id=new_uuid(), actor_user_id=new_uuid(), actor_branch_id=new_uuid(),
            source_module=origen, source_document_id=documento)
        assert not r.success and "Corrección manual" in r.message


def _correct(conn, cuenta, puntos, **kw):
    from backend.application.loyalty.use_cases.ledger_use_cases import (
        AdjustLoyaltyPointsUseCase,
    )
    valores = {"reason_code": "CORTESIA", "source_document": "Queja Q-1",
               "requested_by": new_uuid(), "authorizer_user_id": new_uuid(), **kw}
    return AdjustLoyaltyPointsUseCase(_permissive()).execute(
        conn, loyalty_account_id=cuenta, points_amount=Decimal(puntos),
        actor_branch_id=new_uuid(), operation_id=new_uuid(), **valores)


def test_manual_correction_needs_document_respects_caps_and_another_person(loyalty_conn):
    cuenta = _account(loyalty_conn)
    assert "documento" in _correct(loyalty_conn, cuenta, 10, source_document=" ").message
    mismo = new_uuid()
    assert not _correct(loyalty_conn, cuenta, 10, requested_by=mismo,
                        authorizer_user_id=mismo).success          # segregación
    assert "500" in _correct(loyalty_conn, cuenta, 501).message     # tope por corrección
    assert _correct(loyalty_conn, cuenta, 500).success
    assert _correct(loyalty_conn, cuenta, 500).success
    excedido = _correct(loyalty_conn, cuenta, 1)                    # tope diario 1000
    assert not excedido.success and "tope diario" in excedido.message
    assert _correct(loyalty_conn, cuenta, -100).success             # quitar no topa el día
    fila = loyalty_conn.execute(
        "SELECT source_document_type, notes, point_value FROM loyalty_transactions"
        " WHERE transaction_type='ADJUSTMENT' LIMIT 1").fetchone()
    assert fila["source_document_type"] == "MANUAL_CORRECTION"
    assert "Queja Q-1" in fila["notes"] and fila["point_value"]


def test_the_desktop_offers_only_the_controlled_correction():
    from frontend.desktop.modules.fidelidad.records.catalog import POINT_ACCOUNTS
    comandos = {a.command for a in POINT_ACCOUNTS.actions}
    assert comandos == {"adjust_points"}
    (accion,) = POINT_ACCOUNTS.actions
    assert {f.key for f in accion.fields} >= {"source_document", "authorizer_user_id"}


# ── FID-06: actor, permiso y sucursal de la sesión ──────────────────────────
class _Session:
    def __init__(self, user_id, branch, assigned=(), perms=("GROWTH_ENGINE.puntos.ver",)):
        self.user_id, self.active_branch_id, self.is_active = user_id, branch, True
        self.assigned_branch_ids = frozenset(assigned)
        self._perms = set(perms)

    def tiene_permiso(self, code):
        return code in self._perms


def _session_policy(session):
    from backend.application.loyalty.authorization import LoyaltyAuthorizationPolicy
    from backend.application.loyalty.session_authorization import (
        LoyaltySessionPermissionChecker,
    )
    return LoyaltyAuthorizationPolicy(LoyaltySessionPermissionChecker(session))


def test_member_profile_requires_an_actor_with_permission(loyalty_conn):
    from backend.application.loyalty.queries.member_profile_query_service import (
        LoyaltyMemberProfileQueryService,
    )
    from backend.domain.loyalty.exceptions import LoyaltyPermissionDeniedError

    quien = new_uuid()
    with pytest.raises(LoyaltyPermissionDeniedError):
        LoyaltyMemberProfileQueryService(loyalty_conn).get_profile(new_uuid())
    servicio = LoyaltyMemberProfileQueryService(
        loyalty_conn, authorization=_session_policy(_Session(quien, "b1")))
    with pytest.raises(LoyaltyPermissionDeniedError):
        servicio.get_profile(new_uuid(), actor_user_id=new_uuid())   # otra persona
    assert servicio.get_profile(new_uuid(), actor_user_id=quien).found is False
    sin_permiso = LoyaltyMemberProfileQueryService(
        loyalty_conn, authorization=_session_policy(_Session(quien, "b1", perms=())))
    with pytest.raises(LoyaltyPermissionDeniedError):
        sin_permiso.get_profile(new_uuid(), actor_user_id=quien)


def test_commands_cannot_claim_a_branch_outside_the_session(loyalty_conn):
    from backend.application.loyalty.use_cases.ledger_use_cases import (
        RedeemLoyaltyPointsUseCase,
    )
    quien = new_uuid()
    _award_points(loyalty_conn, customer_id=(cliente := new_uuid()), points=100)
    cuenta = loyalty_conn.execute("SELECT id FROM loyalty_accounts WHERE customer_id=?",
                                  (cliente,)).fetchone()[0]
    b1, b2, b9 = new_uuid(), new_uuid(), new_uuid()
    politica = _session_policy(_Session(quien, b1, assigned=(b2,),
                                        perms=("GROWTH_ENGINE.puntos.canjear",)))
    ajena = RedeemLoyaltyPointsUseCase(politica).execute(
        loyalty_conn, loyalty_account_id=cuenta, points_amount=Decimal("10"),
        operation_id=new_uuid(), actor_user_id=quien, actor_branch_id=b9,
        source_module="sales", sale_id=new_uuid())
    assert not ajena.success and "sucursal" in ajena.message
    asignada = RedeemLoyaltyPointsUseCase(politica).execute(
        loyalty_conn, loyalty_account_id=cuenta, points_amount=Decimal("10"),
        operation_id=new_uuid(), actor_user_id=quien, actor_branch_id=b2,
        source_module="sales", sale_id=new_uuid())
    assert asignada.success


# ── FID-04: una sola base elegible; vale nunca, crédito al cobrarse ─────────
from tests.integration.loyalty.test_sale_points_accrual import (  # noqa: E402
    _balance as _points_of,
    _completed,
    conn as accrual_conn,  # noqa: F401 - fixture reutilizado
)


def _sale_event(customer, total, payments):
    return _completed(customer=customer, total=total, payments=payments)


def test_paying_with_vouchers_never_earns(accrual_conn):
    from backend.application.loyalty.integrations.sales_events import SaleLoyaltyEventHandlers

    cliente = new_uuid()
    manejador = SaleLoyaltyEventHandlers(accrual_conn)
    manejador.on_sale_completed(_sale_event(cliente, "200",
                                            [{"method": "VOUCHER", "amount": "200"}]))
    assert _points_of(accrual_conn, cliente) == 0
    manejador.on_sale_completed(_sale_event(cliente, "200",
                                            [{"method": "CASH", "amount": "120"},
                                             {"method": "VOUCHER", "amount": "80"}]))
    assert _points_of(accrual_conn, cliente) == 12            # sólo el efectivo


def test_preview_and_confirmed_sale_use_the_same_base(accrual_conn):
    from backend.application.loyalty.queries.customer_benefits_query import (
        LoyaltyAccrualEvaluator,
    )
    cliente = new_uuid()
    pagos = [{"method": "CASH", "amount": "120"}, {"method": "VOUCHER", "amount": "80"},
             {"method": "CREDIT", "amount": "50"}]
    vista = LoyaltyAccrualEvaluator(accrual_conn).evaluate(
        customer_id=cliente, branch_id=new_uuid(), total="250", payments=pagos)
    assert vista.points == 12


def _receivable_tables(conn, sale_id):
    conn.executescript(
        "CREATE TABLE IF NOT EXISTS financial_documents (id TEXT PRIMARY KEY,"
        " source_module TEXT, source_document_id TEXT);"
        "CREATE TABLE IF NOT EXISTS receivables (id TEXT PRIMARY KEY,"
        " financial_document_id TEXT);")
    documento, cxc = new_uuid(), new_uuid()
    conn.execute("INSERT INTO financial_documents VALUES (?, 'sales', ?)", (documento, sale_id))
    conn.execute("INSERT INTO receivables VALUES (?, ?)", (cxc, documento))
    conn.commit()
    return cxc


def test_credit_sale_earns_when_collected_once_per_application(accrual_conn):
    from backend.application.loyalty.integrations.credit_collection import (
        CreditCollectionLoyaltyHandler,
    )
    from backend.application.loyalty.integrations.sales_events import SaleLoyaltyEventHandlers

    cliente = new_uuid()
    venta = _sale_event(cliente, "200", [{"method": "CREDIT", "amount": "200"}])
    SaleLoyaltyEventHandlers(accrual_conn).on_sale_completed(venta)
    assert _points_of(accrual_conn, cliente) == 0                # no al vender
    pendiente = accrual_conn.execute(
        "SELECT credit_amount, deferred_points, status FROM loyalty_deferred_accruals"
        " WHERE sale_id=?", (venta["entity_id"],)).fetchone()
    assert (pendiente["deferred_points"], pendiente["status"]) == ("20", "OPEN")

    cxc = _receivable_tables(accrual_conn, venta["entity_id"])
    cobro = CreditCollectionLoyaltyHandler(accrual_conn)
    primera = {"entity_id": new_uuid(), "receivable_id": cxc, "applied_amount": "100.00"}
    cobro.handle(primera)
    cobro.handle(primera)                                        # reintento del despacho
    assert _points_of(accrual_conn, cliente) == 10
    cobro.handle({"entity_id": new_uuid(), "receivable_id": cxc, "applied_amount": "100.00"})
    assert _points_of(accrual_conn, cliente) == 20
    estado = accrual_conn.execute("SELECT status FROM loyalty_deferred_accruals"
                                  " WHERE sale_id=?", (venta["entity_id"],)).fetchone()[0]
    assert estado == "CLOSED"


def test_a_return_before_collection_shrinks_what_is_still_pending(accrual_conn):
    from backend.application.loyalty.integrations.sales_events import SaleLoyaltyEventHandlers

    cliente = new_uuid()
    venta = _sale_event(cliente, "200", [{"method": "CREDIT", "amount": "200"}])
    manejador = SaleLoyaltyEventHandlers(accrual_conn)
    manejador.on_sale_completed(venta)
    manejador.on_sale_returned({**venta, "event_id": new_uuid(),
                                "payload": {"customer_id": cliente, "sale_total": "200",
                                            "refunded_total": "50", "return_id": new_uuid()}})
    pendiente = accrual_conn.execute(
        "SELECT deferred_points, credit_amount FROM loyalty_deferred_accruals"
        " WHERE sale_id=?", (venta["entity_id"],)).fetchone()
    assert pendiente["deferred_points"] == "15" and pendiente["credit_amount"] == "150.00"


# ── FID-03: ningún beneficio se come el margen protegido ────────────────────
def test_budget_policy_protects_margin_and_refuses_lines_without_cost():
    from backend.domain.loyalty.policies.benefit_budget_policy import (
        BenefitBudgetPolicy,
        BudgetLine,
    )
    caro = BudgetLine("p1", "Arrachera", Decimal("100"), Decimal("95"), Decimal("0.10"))
    presupuesto = BenefitBudgetPolicy.compute([caro])
    assert presupuesto.available == Decimal("0.00")            # $100 − $95 − $10 < 0
    sano = BudgetLine("p2", "Huevo", Decimal("100"), Decimal("60"), Decimal("0.10"))
    presupuesto = BenefitBudgetPolicy.compute([caro, sano], committed=Decimal("5"))
    assert (presupuesto.room, presupuesto.available) == (Decimal("30.00"), Decimal("25.00"))
    sin = BudgetLine("p3", "Granel", Decimal("50"), None, Decimal("0.10"))
    con_hueco = BenefitBudgetPolicy.compute([sano, sin])
    assert con_hueco.lines_without_cost == ("Granel",)
    assert not BenefitBudgetPolicy.allows(con_hueco, Decimal("1"))
    assert "Granel" in con_hueco.explain()


def _with_costs(monkeypatch, costos: dict):
    import backend.application.sales.cost_lookup as lookup

    def falso(connection, sale, *, costs=None, virtual=None):
        encontrados = {ln.product_id: Decimal(costos[ln.product_id])
                       for ln in sale.goods_lines if costos.get(ln.product_id) is not None}
        return encontrados, sorted({ln.product_id for ln in sale.goods_lines} - set(encontrados))

    monkeypatch.setattr(lookup, "sale_unit_costs", falso)


def _product_of(conn, sale_id):
    return SaleRepository(conn).get(sale_id).goods_lines[0].product_id


def test_points_are_trimmed_to_the_margin_and_refused_without_cost(loyalty_conn, monkeypatch):
    set_setting(loyalty_conn, "loyalty.point_value", "0.10")
    sale_id, cashier = _sale_with_points(loyalty_conn, points=1000, price="100.00")
    producto = _product_of(loyalty_conn, sale_id)
    _with_costs(monkeypatch, {producto: None})
    sin_costo = _redeem().execute(loyalty_conn, sale_id=sale_id, points=100,
                                  actor_user_id=cashier, operation_id=new_uuid())
    assert not sin_costo.success and sin_costo.error_code == "MARGIN_PROTECTED"
    # costo $85, margen 10 % → caben $5 = 50 puntos aunque el tope % permita 500
    _with_costs(monkeypatch, {producto: "85"})
    recortado = _redeem().execute(loyalty_conn, sale_id=sale_id, points=300,
                                  actor_user_id=cashier, operation_id=new_uuid())
    assert recortado.success and recortado.data["points_redeemed"] == 50
    assert SaleRepository(loyalty_conn).get(sale_id).loyalty_redeemed_amount == Decimal("5.00")


def test_margin_floor_by_category_and_product_exception(loyalty_conn):
    from backend.application.sales.queries.benefit_budget_query import SaleBenefitBudgetQuery
    from backend.infrastructure.db.repositories.loyalty.margin_floor_repository import (
        LoyaltyMarginFloorRepository,
    )
    loyalty_conn.executescript(
        "CREATE TABLE IF NOT EXISTS products (id TEXT PRIMARY KEY, name TEXT, category_id TEXT);"
        "CREATE TABLE IF NOT EXISTS product_categories (id TEXT PRIMARY KEY, name TEXT,"
        " parent_id TEXT);")
    padre, hija = new_uuid(), new_uuid()
    p_hija, p_excepcion, p_suelto = new_uuid(), new_uuid(), new_uuid()
    loyalty_conn.execute("INSERT INTO product_categories VALUES (?, 'Carnes', NULL)", (padre,))
    loyalty_conn.execute("INSERT INTO product_categories VALUES (?, 'Res', ?)", (hija, padre))
    for producto in (p_hija, p_excepcion):
        loyalty_conn.execute("INSERT INTO products VALUES (?, 'x', ?)", (producto, hija))
    repo = LoyaltyMarginFloorRepository(loyalty_conn)
    repo.save(scope_type="CATEGORY", scope_id=padre, min_margin_percent=Decimal("20"),
              actor_user_id=new_uuid())
    repo.save(scope_type="PRODUCT", scope_id=p_excepcion, min_margin_percent=Decimal("5"),
              actor_user_id=new_uuid())
    margenes = SaleBenefitBudgetQuery(loyalty_conn).margins([p_hija, p_excepcion, p_suelto])
    assert margenes == {p_hija: Decimal("0.2"), p_excepcion: Decimal("0.05"),
                        p_suelto: Decimal("0.1")}
