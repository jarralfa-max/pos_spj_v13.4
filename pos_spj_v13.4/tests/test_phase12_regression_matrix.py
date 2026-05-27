from core.services.sales.cart_calculator import CartCalculator
from core.services.sales.payment_policy import PaymentPolicy
from core.use_cases.venta import DatosPago


def test_venta_metodos_pago_basicos_matrix():
    methods = ["Efectivo", "Tarjeta", "Transferencia", "Crédito", "Pago Mixto", "Mercado Pago"]
    normalized = [PaymentPolicy.normalize_payment_method(m) for m in methods]
    assert normalized == methods


def test_descuento_global_y_linea_y_puntos_preview():
    items = [
        {"cantidad": 2, "precio_unitario": 100, "total": 180},  # desc línea 20
        {"cantidad": 1, "precio_unitario": 50, "total": 50},
    ]
    r = CartCalculator.calculate(items, global_discount=10, loyalty_discount=5)
    assert r["descuento_lineas"] == 20
    assert r["subtotal"] == 215
    assert r["puntos_preview"] == 215


def test_credito_sin_credito_suficiente_detectable_por_policy_hook():
    # La policy indica si es crédito; el rechazo de límite lo hace customer_service en SalesService
    assert PaymentPolicy.is_credit_sale("Crédito") is True


def test_mercadopago_pendiente_no_genera_cambio():
    r = PaymentPolicy.validate_payment(total=100, method="Mercado Pago", amount_paid=0)
    assert r["ok"] is True
    assert r["change"] == 0.0


def test_datos_pago_operation_id_y_normalizacion():
    dp = DatosPago(forma_pago="credito", monto_pagado=0, operation_id="op-xyz", puntos_canjeados=5)
    assert dp.forma_pago in ("Crédito", "Credito")
    assert dp.operation_id == "op-xyz"
    assert dp.puntos_canjeados == 5
