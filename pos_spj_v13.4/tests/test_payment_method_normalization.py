from core.services.payment_normalization import (
    normalize_payment_method,
    is_credit_sale,
    is_deferred_payment,
)


def test_normalize_credito_accented():
    assert normalize_payment_method("Crédito") == "Credito"


def test_normalize_credito_plain():
    assert normalize_payment_method("Credito") == "Credito"


def test_normalize_credito_lower_accented():
    assert normalize_payment_method("crédito") == "Credito"


def test_normalize_mercado_pago_title():
    assert normalize_payment_method("Mercado Pago") == "Mercado Pago"


def test_normalize_mercadopago_compact():
    assert normalize_payment_method("mercadopago") == "Mercado Pago"


def test_normalize_pago_mixto():
    assert normalize_payment_method("Pago Mixto") == "Pago Mixto"


def test_is_credit_sale_with_accent():
    assert is_credit_sale("Crédito") is True


def test_is_deferred_payment_mercado_pago():
    assert is_deferred_payment("Mercado Pago") is True


def test_is_deferred_payment_credito():
    assert is_deferred_payment("Credito") is True
