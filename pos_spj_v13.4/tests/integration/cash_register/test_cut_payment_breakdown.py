"""SDLC-PAY-005 — el Corte X/Z desglosa lo cobrado por medio de pago.

Antes los cortes leían sólo el libro de efectivo: `payment_allocations` se
escribía en cada venta y nadie la leía.
"""
from __future__ import annotations

from decimal import Decimal

from backend.application.cash_register.authorization import CashAuthorizationPolicy
from backend.application.cash_register.x_cut_use_cases import GenerateXCutUseCase
from backend.domain.cash_register.cut_breakdown import cut_payment_lines, payment_breakdown
from backend.shared.ids import new_uuid
from tests.integration.test_sales_checkout_settles_everything import (  # noqa: F401
    bus,
    conn,
    mostrador,
)


class _Todo:
    def has_permission(self, *args, **kwargs):
        return True

    def can_access_branch(self, *args, **kwargs):
        return True


_AUTH = CashAuthorizationPolicy(_Todo(), _Todo())


def _venta(presenter, producto, cantidad, *pagos):
    sid = presenter.start_sale().entity_id
    assert presenter.add_line(sale_id=sid, product_id=producto, quantity=Decimal(cantidad),
                              unit_price=Decimal("1"), product_snapshot={"name": "Pollo"}).success
    assert presenter.begin_checkout(sale_id=sid).success
    for method, amount, reference in pagos:
        r = presenter.record_payment(sale_id=sid, method=method, amount=Decimal(amount),
                                     reference=reference)
        assert r.success, r.message
    r = presenter.checkout_sale(sale_id=sid)
    assert r.success, r.message
    return sid


def _corte_x(conn, branch):
    shift_id, cashier = conn.execute(
        "SELECT id, cashier_user_id FROM cash_shifts WHERE branch_id=?", (branch,)).fetchone()
    result = GenerateXCutUseCase(_AUTH).execute(
        conn, shift_id=shift_id, branch_id=branch, actor_user_id=cashier,
        operation_id=new_uuid())
    import json
    return json.loads(conn.execute("SELECT snapshot_json FROM cash_cuts WHERE id=?",
                                   (result.entity_id,)).fetchone()[0])


def test_el_corte_x_separa_cada_medio_con_conteo_y_bruto(conn, mostrador):
    presenter, pollo, _wh, branch = mostrador
    # Venta mixta: efectivo con cambio + Mercado Pago + tarjeta.
    _venta(presenter, pollo, "2", ("CASH", "100", None), ("MERCADO_PAGO", "60", "MP-1"
           "0001"), ("CARD", "40", "AUT-0001"))
    _venta(presenter, pollo, "1", ("MERCADO_PAGO", "100", "MP-20002"))
    _venta(presenter, pollo, "1", ("TRANSFER", "100", "RASTREO-1"))

    snapshot = _corte_x(conn, branch)

    assert snapshot["payment.CASH.count"] == "1"
    assert snapshot["payment.CASH.gross"] == "100"
    assert snapshot["payment.MERCADO_PAGO.count"] == "2"
    assert snapshot["payment.MERCADO_PAGO.gross"] == "160"
    assert snapshot["payment.CARD.count"] == "1"
    assert snapshot["payment.CARD.gross"] == "40"
    assert snapshot["payment.TRANSFER.gross"] == "100"
    assert snapshot["payment.mixed_sales"] == "1"
    assert snapshot["payment.sales"] == "3"
    # El efectivo esperado del cajón no cambia por los medios electrónicos.
    assert Decimal(snapshot["expected_cash"]) == Decimal("100")


def test_el_documento_impreso_lleva_el_desglose():
    lineas = cut_payment_lines({
        "payment.CASH.count": "2", "payment.CASH.gross": "150.00",
        "payment.MERCADO_PAGO.count": "3", "payment.MERCADO_PAGO.gross": "420.50",
        "payment.mixed_sales": "1", "payment.sales": "4",
        "refund.electronic.count": "1", "refund.electronic.amount": "20.00",
        "movement.CASH_SALE": "150.00"})
    assert lineas == (
        ("Efectivo (2)", "150.00"),
        ("Mercado Pago (3)", "420.50"),
        ("Ventas con pago mixto", "1 de 4"),
        ("Reembolsos a medio electrónico (1)", "20.00"),
    )


def test_corte_sin_ventas_no_inventa_lineas():
    assert cut_payment_lines({"movement.OPENING_FLOAT": "500"}) == ()
    assert payment_breakdown([], []) == {}


def test_clasifica_vales_credito_y_otros():
    desglose = payment_breakdown([
        {"payment_record_id": "r1", "method_type": "REFUND_VOUCHER", "amount": "10"},
        {"payment_record_id": "r1", "method_type": "PROMOTIONAL_VOUCHER", "amount": "5"},
        {"payment_record_id": "r2", "method_type": "CUSTOMER_CREDIT", "amount": "70"},
        {"payment_record_id": "r3", "method_type": "PAYMENT_LINK", "amount": "30"},
    ], [{"method": "ORIGINAL_PAYMENT_METHOD", "amount": "12.50"},
        {"method": "CASH", "amount": "3"}])
    assert desglose["payment.VOUCHER.gross"] == "15"
    assert desglose["payment.VOUCHER.count"] == "2"
    assert desglose["payment.CREDIT.gross"] == "70"
    assert desglose["payment.OTHER.gross"] == "30"
    assert desglose["payment.mixed_sales"] == "0"
    assert desglose["refund.electronic.amount"] == "12.50"
    assert desglose["refund.electronic.count"] == "1"
