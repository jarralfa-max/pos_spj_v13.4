"""SDLC-ORD-004 — un pedido descuenta inventario una sola vez, al salir de la
sucursal (decisión del responsable: «al despachar»; en mostrador la mercancía
sale al entregarla), y su reverso devuelve exactamente lo que salió.

Se revisa siempre el saldo Y el libro: antes de este cambio ninguna prueba de
Pedidos miraba ninguno de los dos, y por eso la suite pasaba completa con un
pedido que nunca bajaba la existencia.
"""

from __future__ import annotations

import sqlite3
from decimal import Decimal

import pytest

from backend.application.orders_delivery.authorization import OrdersDeliveryAuthorizationPolicy
from backend.application.orders_delivery.use_cases.delivery_job_use_cases import (
    CreateDeliveryJobUseCase,
)
from backend.application.orders_delivery.use_cases.dispatch_use_cases import (
    ConfirmArrivalUseCase,
    DispatchDeliveryJobUseCase,
    MarkInTransitUseCase,
    RecordDeliveryAttemptUseCase,
)
from backend.application.orders_delivery.use_cases.driver_use_cases import (
    AcceptAssignmentUseCase,
    ProposeAssignmentUseCase,
    RegisterDriverProfileUseCase,
)
from backend.application.orders_delivery.use_cases.inventory_use_cases import (
    ReserveOrderInventoryUseCase,
)
from backend.application.orders_delivery.use_cases.order_capture_use_cases import (
    ConfirmCustomerOrderUseCase,
    CreateCustomerOrderUseCase,
)
from backend.application.orders_delivery.use_cases.pickup_use_cases import (
    CompletePickupUseCase,
    MarkReadyForPickupUseCase,
)
from backend.application.orders_delivery.use_cases.preparation_use_cases import (
    AssignPreparationUseCase,
    CompletePreparationUseCase,
    RecordPreparedLineUseCase,
    StartPreparationUseCase,
)
from backend.application.orders_delivery.use_cases.redelivery_use_cases import (
    ReturnToBranchUseCase,
)
from backend.application.orders_delivery.use_cases.sales_finance_use_cases import (
    ProjectOrderToSaleUseCase,
    RecordOrderPaymentUseCase,
    ReverseCustomerOrderUseCase,
)
from backend.application.orders_delivery.use_cases.substitution_use_cases import (
    AcceptSubstitutionUseCase,
    ProposeSubstitutionUseCase,
)
from backend.application.sales.authorization import (
    AllowAllSalesPermissionCheckerForTests,
    SalesAuthorizationPolicy,
)
from backend.infrastructure.db.repositories.orders_delivery.customer_order_repository import (
    CustomerOrderRepository,
)
from backend.infrastructure.db.schema.inventory_schema import create_inventory_schema
from backend.infrastructure.db.schema.orders_delivery_schema import create_orders_delivery_schema
from backend.infrastructure.db.schema.sales_schema import create_sales_schema
from backend.infrastructure.integrations.orders_delivery_inventory_client import (
    OrdersDeliveryInventoryClient,
)
from backend.shared.ids import new_uuid
from tests.integration._audit_trail_table import create_audit_logs_table
from tests.integration._delivery_address import give_delivery_address
from tests.integration._pos_ready import create_cash_schema, open_cash_shift


class _NoOpWhatsApp:
    def send_message(self, **_kwargs) -> bool:
        return False

    def notify_ready_for_pickup(self, **_kwargs) -> bool:
        return False

    def notify_customer_approval_required(self, **_kwargs) -> bool:
        return False


@pytest.fixture
def conn():
    connection = sqlite3.connect(":memory:")
    create_orders_delivery_schema(connection)
    create_audit_logs_table(connection)
    create_inventory_schema(connection)
    create_sales_schema(connection)
    create_cash_schema(connection)
    yield connection
    connection.close()


def _auth() -> OrdersDeliveryAuthorizationPolicy:
    return OrdersDeliveryAuthorizationPolicy.permissive_for_tests()


def _sales_auth() -> SalesAuthorizationPolicy:
    return SalesAuthorizationPolicy(AllowAllSalesPermissionCheckerForTests())


def _stock(conn, *, product_id, branch_id, quantity="100", warehouse_id=None, lot_id=""):
    """Saldo como lo dejan los flujos reales: con ubicación (y lote, si vino de
    Compras). Un saldo sin ubicación no se puede mover: la validación del
    movimiento la exige."""
    conn.execute(
        "INSERT INTO inventory_balances (id, product_id, branch_id, warehouse_id,"
        " location_id, lot_id, serial_id, inventory_status, quantity, weight,"
        " reserved_quantity, reserved_weight, version, updated_at)"
        " VALUES (?,?,?,?,?,?,'','AVAILABLE',?,'0','0','0',0,'t')",
        (new_uuid(), product_id, branch_id, warehouse_id or branch_id, branch_id, lot_id,
         quantity))


def _existencia(conn, product_id) -> tuple[Decimal, Decimal]:
    filas = conn.execute(
        "SELECT quantity, reserved_quantity FROM inventory_balances WHERE product_id=?",
        (product_id,)).fetchall()
    return (sum((Decimal(f[0]) for f in filas), Decimal("0")),
            sum((Decimal(f[1]) for f in filas), Decimal("0")))


def _movimientos(conn, tipo) -> list[tuple]:
    """(producto, cantidad, lote, ubicación) de cada línea del libro de ese tipo."""
    return conn.execute(
        "SELECT l.product_id, l.quantity, l.lot_id, COALESCE(NULLIF(l.from_location_id,''),"
        " l.to_location_id) FROM inventory_ledger_lines l JOIN inventory_ledger m"
        " ON m.id = l.movement_id WHERE m.movement_type=?", (tipo,)).fetchall()


def _reservas(conn, product_id=None) -> list[str]:
    sql, params = "SELECT status FROM inventory_reservation", ()
    if product_id:
        sql, params = sql + " WHERE product_id=?", (product_id,)
    return [f[0] for f in conn.execute(sql, params).fetchall()]


def _preparar(conn, order_id, *, prepared=("1",)):
    ConfirmCustomerOrderUseCase(_auth()).execute(
        conn, order_id=order_id, actor_user_id=new_uuid(), operation_id=new_uuid())
    reserva = ReserveOrderInventoryUseCase(_auth()).execute(
        conn, order_id=order_id, actor_user_id=new_uuid(), operation_id=new_uuid())
    assert reserva.success, reserva.message
    AssignPreparationUseCase(_auth()).execute(
        conn, order_id=order_id, assigned_to_user_id=new_uuid(),
        actor_user_id=new_uuid(), operation_id=new_uuid())
    StartPreparationUseCase(_auth()).execute(
        conn, order_id=order_id, actor_user_id=new_uuid(), operation_id=new_uuid())
    lineas = CustomerOrderRepository(conn).get(order_id).lines
    for linea, cantidad in zip(lineas, prepared):
        RecordPreparedLineUseCase(_auth()).execute(
            conn, order_id=order_id, line_id=linea.id, quantity=cantidad,
            actor_user_id=new_uuid(), operation_id=new_uuid())


def _terminar_preparacion(conn, order_id):
    resultado = CompletePreparationUseCase(_auth()).execute(
        conn, order_id=order_id, actor_user_id=new_uuid(), operation_id=new_uuid())
    assert resultado.success, resultado.message


def _pedido_mostrador(conn, *, branch_id, product_id, requested="1", prepared="1"):
    creado = CreateCustomerOrderUseCase(_auth()).execute(
        conn, branch_id=branch_id, channel="POS", order_type="STANDARD",
        fulfillment_type="COUNTER",
        lines=[{"product_id": product_id, "unit_price": "10.00",
                "requested_quantity": requested}],
        actor_user_id=new_uuid(), operation_id=new_uuid())
    assert creado.success, creado.message
    _preparar(conn, creado.entity_id, prepared=(prepared,))
    _terminar_preparacion(conn, creado.entity_id)
    listo = MarkReadyForPickupUseCase(_auth(), whatsapp_client=_NoOpWhatsApp()).execute(
        conn, order_id=creado.entity_id, actor_user_id=new_uuid(), operation_id=new_uuid())
    assert listo.success, listo.message
    return creado.entity_id, listo.data["verification_code"]


def _cobrar(conn, order_id):
    cajero = new_uuid()
    open_cash_shift(conn, branch_id=CustomerOrderRepository(conn).get(order_id).branch_id,
                    cashier_user_id=cajero)
    proyeccion = ProjectOrderToSaleUseCase(_auth()).execute(
        conn, order_id=order_id, cashier_user_id=cajero, actor_user_id=new_uuid(),
        operation_id=new_uuid(), sales_authorization=_sales_auth())
    assert proyeccion.success, proyeccion.message
    total = conn.execute("SELECT total FROM sales WHERE id=?",
                         (proyeccion.data["sale_id"],)).fetchone()[0]
    pago = RecordOrderPaymentUseCase(_auth()).execute(
        conn, order_id=order_id, method="CASH", amount=Decimal(str(total)),
        actor_user_id=new_uuid(), operation_id=new_uuid(),
        sales_authorization=_sales_auth())
    assert pago.success, pago.message
    return proyeccion.data["sale_id"]


def _entregar_en_mostrador(conn, order_id, codigo):
    return CompletePickupUseCase(_auth()).execute(
        conn, order_id=order_id, presented_code=codigo,
        actor_user_id=new_uuid(), operation_id=new_uuid())


def _pedido_a_domicilio(conn, *, branch_id, product_id, requested="1", prepared="1"):
    creado = CreateCustomerOrderUseCase(_auth()).execute(
        conn, branch_id=branch_id, channel="WHATSAPP", order_type="STANDARD",
        fulfillment_type="HOME_DELIVERY",
        lines=[{"product_id": product_id, "unit_price": "10.00",
                "requested_quantity": requested}],
        actor_user_id=new_uuid(), operation_id=new_uuid())
    order_id = creado.entity_id
    give_delivery_address(conn, order_id, branch_id=branch_id, authorization=_auth())
    _preparar(conn, order_id, prepared=(prepared,))
    _terminar_preparacion(conn, order_id)
    job_id = CreateDeliveryJobUseCase(_auth()).execute(
        conn, order_id=order_id, branch_id=branch_id, actor_user_id=new_uuid(),
        operation_id=new_uuid()).entity_id
    driver_id = new_uuid()
    RegisterDriverProfileUseCase(_auth()).execute(
        conn, driver_id=driver_id, branch_id=branch_id, actor_user_id=new_uuid(),
        operation_id=new_uuid())
    propuesta = ProposeAssignmentUseCase(_auth()).execute(
        conn, delivery_job_id=job_id, driver_id=driver_id, actor_user_id=new_uuid(),
        operation_id=new_uuid())
    AcceptAssignmentUseCase(_auth()).execute(
        conn, assignment_id=propuesta.entity_id, actor_user_id=new_uuid(),
        operation_id=new_uuid())
    return job_id, order_id


def _despachar(conn, job_id):
    return DispatchDeliveryJobUseCase(_auth(), whatsapp_client=_NoOpWhatsApp()).execute(
        conn, delivery_job_id=job_id, actor_user_id=new_uuid(), operation_id=new_uuid())


def _llegar(conn, job_id):
    for caso in (MarkInTransitUseCase, ConfirmArrivalUseCase):
        resultado = caso(_auth()).execute(
            conn, delivery_job_id=job_id, actor_user_id=new_uuid(), operation_id=new_uuid())
        assert resultado.success, resultado.message


class TestMostrador:
    def test_la_existencia_baja_al_entregar_y_la_reserva_queda_cumplida(self, conn):
        branch_id, product_id = new_uuid(), new_uuid()
        _stock(conn, product_id=product_id, branch_id=branch_id)
        order_id, codigo = _pedido_mostrador(conn, branch_id=branch_id, product_id=product_id)
        _cobrar(conn, order_id)
        assert _existencia(conn, product_id) == (Decimal("100"), Decimal("1"))

        resultado = _entregar_en_mostrador(conn, order_id, codigo)

        assert resultado.success, resultado.message
        assert _existencia(conn, product_id) == (Decimal("99"), Decimal("0"))
        assert _reservas(conn) == ["FULFILLED"]
        salidas = _movimientos(conn, "SALE_ISSUE")
        assert len(salidas) == 1 and Decimal(salidas[0][1]) == Decimal("1")

    def test_descuenta_la_cantidad_preparada_no_la_pedida(self, conn):
        branch_id, product_id = new_uuid(), new_uuid()
        _stock(conn, product_id=product_id, branch_id=branch_id)
        order_id, codigo = _pedido_mostrador(
            conn, branch_id=branch_id, product_id=product_id, requested="5", prepared="4")
        _cobrar(conn, order_id)

        assert _entregar_en_mostrador(conn, order_id, codigo).success

        assert _existencia(conn, product_id) == (Decimal("96"), Decimal("0"))

    def test_sin_mas_existencia_que_la_reservada_tambien_sale(self, conn):
        """La salida va antes de soltar la retención: con todo reservado, el
        movimiento no debe chocar contra su propia reserva."""
        branch_id, product_id = new_uuid(), new_uuid()
        _stock(conn, product_id=product_id, branch_id=branch_id, quantity="1")
        order_id, codigo = _pedido_mostrador(conn, branch_id=branch_id, product_id=product_id)
        _cobrar(conn, order_id)

        resultado = _entregar_en_mostrador(conn, order_id, codigo)

        assert resultado.success, resultado.message
        assert _existencia(conn, product_id) == (Decimal("0"), Decimal("0"))

    def test_preparar_de_mas_sale_de_lo_disponible_y_si_no_alcanza_no_entrega(self, conn):
        branch_id, product_id = new_uuid(), new_uuid()
        _stock(conn, product_id=product_id, branch_id=branch_id, quantity="1")
        order_id, codigo = _pedido_mostrador(
            conn, branch_id=branch_id, product_id=product_id, requested="1", prepared="3")
        _cobrar(conn, order_id)

        resultado = _entregar_en_mostrador(conn, order_id, codigo)

        assert not resultado.success
        assert resultado.error_code == "INVENTORY_COMMIT_FAILED"
        # Todo o nada: ni la existencia ni la reserva ni el pedido se movieron.
        assert _existencia(conn, product_id) == (Decimal("1"), Decimal("1"))
        assert _reservas(conn) == ["CONFIRMED"]
        assert CustomerOrderRepository(conn).get(order_id).status.value == "IN_FULFILLMENT"


class TestDomicilio:
    def test_descuenta_al_despachar_no_antes_ni_despues(self, conn):
        branch_id, product_id = new_uuid(), new_uuid()
        _stock(conn, product_id=product_id, branch_id=branch_id)
        job_id, _order_id = _pedido_a_domicilio(conn, branch_id=branch_id, product_id=product_id)
        assert _existencia(conn, product_id) == (Decimal("100"), Decimal("1"))

        despacho = _despachar(conn, job_id)

        assert despacho.success, despacho.message
        assert _existencia(conn, product_id) == (Decimal("99"), Decimal("0"))
        assert _reservas(conn) == ["FULFILLED"]

        _llegar(conn, job_id)
        entrega = RecordDeliveryAttemptUseCase(_auth(), whatsapp_client=_NoOpWhatsApp()).execute(
            conn, delivery_job_id=job_id, successful=True, actor_user_id=new_uuid(),
            operation_id=new_uuid(), recipient_name="Cliente", pin_verified=True)
        assert entrega.success, entrega.message
        assert _existencia(conn, product_id) == (Decimal("99"), Decimal("0"))
        assert len(_movimientos(conn, "SALE_ISSUE")) == 1

    def test_un_despacho_que_no_puede_descontar_no_despacha(self, conn):
        branch_id, product_id = new_uuid(), new_uuid()
        _stock(conn, product_id=product_id, branch_id=branch_id, quantity="1")
        job_id, order_id = _pedido_a_domicilio(
            conn, branch_id=branch_id, product_id=product_id, requested="1", prepared="2")

        despacho = _despachar(conn, job_id)

        assert not despacho.success
        assert despacho.error_code == "INVENTORY_COMMIT_FAILED"
        assert CustomerOrderRepository(conn).get(order_id).fulfillment_status.value == "READY"
        assert _existencia(conn, product_id) == (Decimal("1"), Decimal("1"))

    def test_regreso_a_sucursal_devuelve_lo_que_salio(self, conn):
        """Se descuenta al despachar, así que una entrega que no se logró y
        regresa tiene que volver a contarse."""
        branch_id, product_id = new_uuid(), new_uuid()
        _stock(conn, product_id=product_id, branch_id=branch_id)
        job_id, _order_id = _pedido_a_domicilio(conn, branch_id=branch_id, product_id=product_id)
        assert _despachar(conn, job_id).success
        _llegar(conn, job_id)
        fallo = RecordDeliveryAttemptUseCase(_auth(), whatsapp_client=_NoOpWhatsApp()).execute(
            conn, delivery_job_id=job_id, successful=False, actor_user_id=new_uuid(),
            operation_id=new_uuid(), failure_reason="CUSTOMER_NOT_HOME",
        )
        assert fallo.success, fallo.message

        regreso = ReturnToBranchUseCase(_auth()).execute(
            conn, delivery_job_id=job_id, actor_user_id=new_uuid(), operation_id=new_uuid())

        assert regreso.success, regreso.message
        assert _existencia(conn, product_id) == (Decimal("100"), Decimal("0"))
        filas = conn.execute("SELECT COUNT(*) FROM inventory_balances WHERE product_id=?",
                             (product_id,)).fetchone()
        assert filas[0] == 1, "la devolución partió el saldo en otra fila"


class TestReverso:
    def _pedido_completado(self, conn, *, lot_id=""):
        branch_id, product_id = new_uuid(), new_uuid()
        _stock(conn, product_id=product_id, branch_id=branch_id, lot_id=lot_id)
        order_id, codigo = _pedido_mostrador(conn, branch_id=branch_id, product_id=product_id)
        _cobrar(conn, order_id)
        assert _entregar_en_mostrador(conn, order_id, codigo).success
        return order_id, product_id

    def _reversar(self, conn, order_id):
        return ReverseCustomerOrderUseCase(_auth()).execute(
            conn, order_id=order_id, reason="Cliente devolvió", actor_user_id=new_uuid(),
            authorizer_user_id=new_uuid(), operation_id=new_uuid(),
            sales_authorization=_sales_auth())

    def test_devuelve_exactamente_lo_que_salio(self, conn):
        order_id, product_id = self._pedido_completado(conn)

        resultado = self._reversar(conn, order_id)

        assert resultado.success, resultado.message
        assert _existencia(conn, product_id) == (Decimal("100"), Decimal("0"))
        entradas = _movimientos(conn, "SALE_RETURN")
        assert len(entradas) == 1 and Decimal(entradas[0][1]) == Decimal("1")
        filas = conn.execute("SELECT COUNT(*) FROM inventory_balances WHERE product_id=?",
                             (product_id,)).fetchone()
        assert filas[0] == 1, "la devolución partió el saldo en otra fila"

    def test_vuelve_al_lote_del_que_salio(self, conn):
        lote = new_uuid()
        order_id, product_id = self._pedido_completado(conn, lot_id=lote)

        assert self._reversar(conn, order_id).success

        fila = conn.execute(
            "SELECT lot_id, quantity FROM inventory_balances WHERE product_id=?",
            (product_id,)).fetchall()
        assert fila == [(lote, "100")]

    def test_un_pedido_que_nunca_desconto_no_suma_y_suelta_su_retencion(self, conn):
        branch_id, product_id = new_uuid(), new_uuid()
        _stock(conn, product_id=product_id, branch_id=branch_id)
        order_id, _codigo = _pedido_mostrador(conn, branch_id=branch_id, product_id=product_id)
        order = CustomerOrderRepository(conn).get(order_id)

        cliente = OrdersDeliveryInventoryClient(conn, branch_id=branch_id)
        cliente.restore_order(order, operation_id=new_uuid(), actor_user_id=new_uuid(),
                              reason_code="ORDER_REVERSAL")
        conn.commit()

        assert _existencia(conn, product_id) == (Decimal("100"), Decimal("0"))
        assert _movimientos(conn, "SALE_RETURN") == []
        assert _reservas(conn) == ["RELEASED"]


class TestSinDobleDescuento:
    def test_un_segundo_cierre_del_mismo_pedido_no_vuelve_a_descontar(self, conn):
        branch_id, product_id = new_uuid(), new_uuid()
        _stock(conn, product_id=product_id, branch_id=branch_id)
        order_id, codigo = _pedido_mostrador(conn, branch_id=branch_id, product_id=product_id)
        _cobrar(conn, order_id)
        assert _entregar_en_mostrador(conn, order_id, codigo).success
        order = CustomerOrderRepository(conn).get(order_id)

        cliente = OrdersDeliveryInventoryClient(conn, branch_id=branch_id)
        cliente.commit_order(order, operation_id=new_uuid(), actor_user_id=new_uuid())
        conn.commit()

        assert _existencia(conn, product_id) == (Decimal("99"), Decimal("0"))
        assert len(_movimientos(conn, "SALE_ISSUE")) == 1

    def test_pedidos_cobra_sin_que_ventas_descuente(self, conn, monkeypatch):
        """`settle_inventory=False`: el cobro del pedido no mueve inventario."""
        import backend.infrastructure.integrations.orders_delivery_sales_client as modulo

        vistos = []
        original = modulo.CheckoutSaleUseCase

        def espia(*args, **kwargs):
            vistos.append(kwargs.get("settle_inventory"))
            return original(*args, **kwargs)

        monkeypatch.setattr(modulo, "CheckoutSaleUseCase", espia)
        branch_id, product_id = new_uuid(), new_uuid()
        _stock(conn, product_id=product_id, branch_id=branch_id)
        order_id, _codigo = _pedido_mostrador(conn, branch_id=branch_id, product_id=product_id)

        _cobrar(conn, order_id)

        assert vistos == [False]
        assert _existencia(conn, product_id) == (Decimal("100"), Decimal("1"))
        assert _movimientos(conn, "SALE_ISSUE") == []

    def test_con_settle_inventory_true_ventas_descuenta_una_sola_vez(self, conn):
        """El otro valor: una venta de mostrador (no pedido) sale por Ventas una
        vez, y Pedidos no participa."""
        from backend.application.sales.use_cases.cart_use_cases import (
            AddSaleLineUseCase,
            StartSaleUseCase,
        )
        from backend.application.sales.use_cases.checkout_use_cases import CheckoutSaleUseCase
        from backend.application.sales.use_cases.lifecycle_use_cases import (
            BeginSaleCheckoutUseCase,
        )
        from backend.application.sales.use_cases.payment_use_cases import (
            RecordSalePaymentUseCase,
        )

        branch_id, product_id, cajero = new_uuid(), new_uuid(), new_uuid()
        _stock(conn, product_id=product_id, branch_id=branch_id)
        auth = _sales_auth()
        venta = StartSaleUseCase(auth).execute(
            conn, branch_id=branch_id, cashier_user_id=cajero, operation_id=new_uuid(),
            actor_user_id=cajero, channel="POS", currency_code="MXN").entity_id
        AddSaleLineUseCase(auth).execute(
            conn, sale_id=venta, product_id=product_id, quantity=Decimal("1"),
            unit_price=Decimal("10"), actor_user_id=cajero, operation_id=new_uuid(),
            quantity_unit="PZA", product_snapshot={})
        BeginSaleCheckoutUseCase(auth).execute(
            conn, sale_id=venta, actor_user_id=cajero, operation_id=new_uuid())
        RecordSalePaymentUseCase(auth).execute(
            conn, sale_id=venta, method="CASH", amount=Decimal("10"), actor_user_id=cajero,
            operation_id=new_uuid())
        from backend.application.inventory.authorization import InventoryAuthorizationPolicy

        resultado = CheckoutSaleUseCase(
            auth, InventoryAuthorizationPolicy.permissive_for_tests(),
            settle_inventory=True, require_cash_shift=False).execute(
            conn, sale_id=venta, actor_user_id=cajero, operation_id=new_uuid())

        assert resultado.success, resultado.message
        assert _existencia(conn, product_id) == (Decimal("99"), Decimal("0"))
        assert len(_movimientos(conn, "SALE_ISSUE")) == 1


class TestExistenciaReal:
    def test_reserva_y_descuenta_del_almacen_de_venta_y_el_lote(self, conn):
        """Medido: `CreateReservationUseCase` buscaba un saldo sin lote en
        almacén = sucursal, una fila que ningún flujo real llena. Lo que entra
        por Compras (almacén de venta, ubicación y lote) debe poder despacharse."""
        branch_id, product_id, almacen, lote = new_uuid(), new_uuid(), new_uuid(), new_uuid()
        conn.execute(
            "INSERT INTO warehouses (id, branch_id, code, name, warehouse_type, status,"
            " allow_sales_allocation, created_at, updated_at)"
            " VALUES (?,?,?,?,?,?,1,'t','t')",
            (almacen, branch_id, "V", "Venta", "STORE", "ACTIVE"))
        _stock(conn, product_id=product_id, branch_id=branch_id, warehouse_id=almacen,
               lot_id=lote)
        order_id, codigo = _pedido_mostrador(conn, branch_id=branch_id, product_id=product_id)
        _cobrar(conn, order_id)

        assert _entregar_en_mostrador(conn, order_id, codigo).success

        assert conn.execute(
            "SELECT warehouse_id, lot_id, quantity, reserved_quantity FROM inventory_balances"
            " WHERE product_id=?", (product_id,)).fetchall() == [(almacen, lote, "99", "0")]


class TestLineasQueNoSalen:
    def _pedido_dos_lineas(self, conn, branch_id, a, b):
        creado = CreateCustomerOrderUseCase(_auth()).execute(
            conn, branch_id=branch_id, channel="POS", order_type="STANDARD",
            fulfillment_type="COUNTER",
            lines=[{"product_id": a, "unit_price": "10.00", "requested_quantity": "1"},
                   {"product_id": b, "unit_price": "10.00", "requested_quantity": "2"}],
            actor_user_id=new_uuid(), operation_id=new_uuid())
        assert creado.success, creado.message
        return creado.entity_id

    def test_dos_lineas_del_mismo_producto_reservan_y_descuentan_ambas(self, conn):
        branch_id, product_id = new_uuid(), new_uuid()
        _stock(conn, product_id=product_id, branch_id=branch_id)
        order_id = self._pedido_dos_lineas(conn, branch_id, product_id, product_id)
        _preparar(conn, order_id, prepared=("1", "2"))
        assert _existencia(conn, product_id) == (Decimal("100"), Decimal("3"))
        _terminar_preparacion(conn, order_id)
        listo = MarkReadyForPickupUseCase(_auth(), whatsapp_client=_NoOpWhatsApp()).execute(
            conn, order_id=order_id, actor_user_id=new_uuid(), operation_id=new_uuid())
        _cobrar(conn, order_id)

        assert _entregar_en_mostrador(conn, order_id, listo.data["verification_code"]).success

        assert _existencia(conn, product_id) == (Decimal("97"), Decimal("0"))

    def test_sustitucion_aceptada_saca_el_sustituto_y_suelta_el_original(self, conn):
        branch_id, original, sustituto = new_uuid(), new_uuid(), new_uuid()
        _stock(conn, product_id=original, branch_id=branch_id)
        _stock(conn, product_id=sustituto, branch_id=branch_id)
        creado = CreateCustomerOrderUseCase(_auth()).execute(
            conn, branch_id=branch_id, channel="POS", order_type="STANDARD",
            fulfillment_type="COUNTER",
            lines=[{"product_id": original, "unit_price": "10.00",
                    "requested_quantity": "1"}],
            actor_user_id=new_uuid(), operation_id=new_uuid())
        order_id = creado.entity_id
        _preparar(conn, order_id)
        linea = CustomerOrderRepository(conn).get(order_id).lines[0]
        propuesta = ProposeSubstitutionUseCase(_auth(), whatsapp_client=_NoOpWhatsApp()).execute(
            conn, order_id=order_id, line_id=linea.id, substitute_product_id=sustituto,
            substitution_type="EQUIVALENT_PRODUCT", new_unit_price=Decimal("10"), reason="Sin original",
            actor_user_id=new_uuid(), operation_id=new_uuid())
        assert propuesta.success, propuesta.message
        aceptada = AcceptSubstitutionUseCase(_auth()).execute(
            conn, order_id=order_id, line_id=linea.id, actor_user_id=new_uuid(),
            operation_id=new_uuid())
        assert aceptada.success, aceptada.message
        _terminar_preparacion(conn, order_id)
        listo = MarkReadyForPickupUseCase(_auth(), whatsapp_client=_NoOpWhatsApp()).execute(
            conn, order_id=order_id, actor_user_id=new_uuid(), operation_id=new_uuid())
        _cobrar(conn, order_id)

        assert _entregar_en_mostrador(conn, order_id, listo.data["verification_code"]).success

        assert _existencia(conn, original) == (Decimal("100"), Decimal("0"))
        assert _existencia(conn, sustituto) == (Decimal("99"), Decimal("0"))
        assert _reservas(conn, original) == ["RELEASED"]
