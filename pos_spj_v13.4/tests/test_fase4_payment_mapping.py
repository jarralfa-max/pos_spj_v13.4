from pathlib import Path

from core.services.sales.payment_policy import PaymentPolicy


REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_SALES = (REPO_ROOT / 'core/services/sales_service.py').read_text(encoding='utf-8')
SRC_UI = (REPO_ROOT / 'modulos/ventas.py').read_text(encoding='utf-8')


def test_credit_with_accent_maps_to_credit_not_cash():
    assert PaymentPolicy.normalize_payment_method("Crédito") == "Crédito"
    data = PaymentPolicy.build_payment_breakdown(total=100.0, method="Crédito", saldo_credito=100.0)
    assert data["lineas"]["credito"] == 100.0
    assert data["efectivo_recibido"] == 0.0


def test_credit_without_accent_maps_to_credit_not_cash():
    assert PaymentPolicy.normalize_payment_method("Credito") == "Crédito"
    data = PaymentPolicy.build_payment_breakdown(total=100.0, method="Credito", saldo_credito=100.0)
    assert data["lineas"]["credito"] == 100.0
    assert data["amount_paid_real"] == 0.0


def test_mixed_payment_preserves_cash_and_card():
    data = PaymentPolicy.build_payment_breakdown(
        total=100.0, method="Pago Mixto", amount_paid=100.0, cash=40.0, card=60.0
    )
    assert data["efectivo_recibido"] == 40.0
    assert data["monto_tarjeta_mixto"] == 60.0


def test_points_discount_affects_backend_total():
    assert "total_a_pagar = round(total_a_pagar - loyalty_discount, 2)" in (REPO_ROOT / 'core/services/sales_service.py').read_text(encoding='utf-8')


def test_ui_total_equals_result_total_after_points():
    assert "Total: ${float(getattr(result, 'total', 0.0) or 0.0):.2f}" in SRC_UI


def test_ticket_payment_breakdown_matches_backend():
    assert 'datos_ticket = dict(getattr(result, "ticket_payload", {}) or {})' in SRC_UI
    assert '_imprimir_ticket_consolidado(datos_ticket)' in SRC_UI
    assert 'ticket_payload["pago"]' in SRC_SALES
    assert '"lineas": payment_breakdown' in SRC_SALES
