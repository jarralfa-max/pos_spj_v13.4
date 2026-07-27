from core.use_cases.venta import (
    DatosPago,
    ClienteVentaDTO,
    PaymentBreakdown,
    LoyaltyRedemptionRequest,
    LoyaltyRedemptionPreview,
    SaleContext,
    ItemCarrito,
)


def test_datos_pago_normaliza_metodos_basicos():
    assert DatosPago(forma_pago="efectivo").forma_pago == "Efectivo"
    assert DatosPago(forma_pago="Tarjeta").forma_pago == "Tarjeta"
    assert DatosPago(forma_pago="transferencia").forma_pago == "Transferencia"
    assert DatosPago(forma_pago="credito").forma_pago == "Crédito"


def test_datos_pago_normaliza_mixto_mercadopago_y_montos():
    dp = DatosPago(
        forma_pago="pago mixto",
        monto_pagado=100,
        pago_mixto={"efectivo": 50, "tarjeta": 50},
        puntos_canjeados="10",
        descuento_global="2.5",
        descuento_lineas="1.5",
        mercado_pago_ref="mp-123",
        operation_id="op-1",
    )
    assert dp.forma_pago == "Mixto"
    assert dp.total_pagado == 100.0
    assert dp.pago_mixto["efectivo"] == 50.0
    assert dp.puntos_canjeados == 10
    assert dp.descuento_global == 2.5
    assert dp.descuento_lineas == 1.5


def test_datos_pago_soporta_credito_y_operation_id_opcional():
    dp = DatosPago(forma_pago="Crédito", cliente_id=None, operation_id="")
    assert dp.forma_pago == "Crédito"
    assert dp.cliente_id is None
    assert dp.operation_id == ""


def test_payment_breakdown_y_cliente_dto_construccion():
    cli = ClienteVentaDTO(cliente_id=7, nombre="Cliente", saldo_credito=150.0, puntos=24)
    pb = PaymentBreakdown(metodo="Mercado Pago", total=500.0, recibido=0.0, pendiente=500.0, operation_id="op-2")
    assert cli.saldo_credito == 150.0
    assert cli.puntos == 24
    assert pb.metodo == "Mercado Pago"
    assert pb.pendiente == 500.0


def test_loyalty_request_preview_y_sale_context():
    req = LoyaltyRedemptionRequest(cliente_id=1, puntos=30, subtotal=400.0, operation_id="op-3")
    preview = LoyaltyRedemptionPreview(
        cliente_id=1,
        puntos_solicitados=30,
        puntos_aplicables=20,
        descuento_aplicable=20.0,
        subtotal=400.0,
        total_estimado=380.0,
    )
    ctx = SaleContext(
        items=[ItemCarrito(producto_id=1, cantidad=1, precio_unit=100)],
        datos_pago=DatosPago(forma_pago="efectivo", monto_pagado=100),
        sucursal_id=2,
        usuario="cajero",
        operation_id="op-ctx",
        loyalty_redemption=req,
    )
    assert req.puntos == 30
    assert preview.total_estimado == 380.0
    assert ctx.sucursal_id == 2
    assert ctx.usuario == "cajero"
    assert ctx.operation_id == "op-ctx"
