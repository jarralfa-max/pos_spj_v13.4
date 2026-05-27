from core.services.sales.cart_calculator import CartCalculator


def test_item_simple():
    r = CartCalculator.calculate([{'cantidad': 2, 'precio_unitario': 10, 'total': 20}])
    assert r['subtotal'] == 20
    assert r['total_final'] == 20


def test_descuento_por_linea():
    r = CartCalculator.calculate([{'cantidad': 2, 'precio_unitario': 10, 'total': 16}])
    assert r['descuento_lineas'] == 4
    assert r['total_final'] == 16


def test_descuento_global():
    r = CartCalculator.calculate([{'cantidad': 2, 'precio_unitario': 10, 'total': 20}], global_discount=5)
    assert r['subtotal'] == 15


def test_pago_mixto_cambio_preview():
    r = CartCalculator.calculate([{'cantidad': 1, 'precio_unitario': 100, 'total': 100}], amount_paid=120)
    assert r['cambio'] == 20


def test_puntos_preview():
    r = CartCalculator.calculate([{'cantidad': 1, 'precio_unitario': 99.9, 'total': 99.9}])
    assert r['puntos_preview'] == 99


def test_redondeos():
    r = CartCalculator.calculate([{'cantidad': 1, 'precio_unitario': 10.555, 'total': 10.555}], iva_rate=0.16)
    assert r['subtotal'] == 10.55
    assert r['impuestos'] == 1.69
    assert r['total_final'] == 12.24
