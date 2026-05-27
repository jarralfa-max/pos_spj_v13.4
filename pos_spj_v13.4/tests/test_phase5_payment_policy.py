from core.services.sales.payment_policy import PaymentPolicy


def test_normalize_payment_method():
    assert PaymentPolicy.normalize_payment_method('credito') == 'Crédito'
    assert PaymentPolicy.normalize_payment_method('mixto') == 'Pago Mixto'
    assert PaymentPolicy.normalize_payment_method('mercadopago') == 'Mercado Pago'


def test_validate_payment_efectivo_y_cambio():
    v = PaymentPolicy.validate_payment(total=100, method='Efectivo', amount_paid=120)
    assert v['ok'] is True
    assert v['change'] == 20


def test_validate_mixed_payment():
    v = PaymentPolicy.validate_mixed_payment(total=100, cash=40, card=60)
    assert v['ok'] is True
    assert v['diff'] == 0


def test_build_payment_breakdown_credito_y_mixto():
    c = PaymentPolicy.build_payment_breakdown(total=200, method='Crédito', saldo_credito=200)
    assert c['saldo_credito'] == 200
    m = PaymentPolicy.build_payment_breakdown(total=100, method='Pago Mixto', cash=30, card=80)
    assert m['monto_tarjeta_mixto'] == 80
    assert m['cambio'] == 10


def test_helpers_credit_pending():
    assert PaymentPolicy.is_credit_sale('Crédito') is True
    assert PaymentPolicy.is_pending_payment('Mercado Pago') is True
