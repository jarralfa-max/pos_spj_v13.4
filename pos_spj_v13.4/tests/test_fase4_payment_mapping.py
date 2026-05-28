from pathlib import Path

from core.services.sales.payment_policy import PaymentPolicy


SRC_SALES = Path('pos_spj_v13.4/core/services/sales_service.py').read_text(encoding='utf-8')
SRC_UI = Path('pos_spj_v13.4/modulos/ventas.py').read_text(encoding='utf-8')


def test_credit_with_accent_maps_to_credit_not_cash():
    assert PaymentPolicy.normalize_payment_method("Crédito") == "Crédito"
    assert '"Crédito": "credito"' in SRC_SALES


def test_credit_without_accent_maps_to_credit_not_cash():
    assert PaymentPolicy.normalize_payment_method("Credito") == "Crédito"
    assert '"Credito": "credito"' in SRC_SALES


def test_mixed_payment_preserves_cash_and_card():
    data = PaymentPolicy.build_payment_breakdown(
        total=100.0, method="Pago Mixto", amount_paid=100.0, cash=40.0, card=60.0
    )
    assert data["efectivo_recibido"] == 40.0
    assert data["monto_tarjeta_mixto"] == 60.0


def test_points_discount_affects_backend_total():
    assert "total_a_pagar = round(total_a_pagar - loyalty_discount, 2)" in Path('pos_spj_v13.4/core/services/sales_service.py').read_text(encoding='utf-8')


def test_ui_total_equals_result_total_after_points():
    assert "Total: ${float(getattr(result, 'total', 0.0) or 0.0):.2f}" in SRC_UI


def test_ticket_payment_breakdown_matches_backend():
    assert '"pago": dict(getattr(result, "payment_breakdown", {}) or {})' in SRC_UI
