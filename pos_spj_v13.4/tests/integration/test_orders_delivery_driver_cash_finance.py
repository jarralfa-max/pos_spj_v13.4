"""SDLC-ORD-001 — el dinero de Pedidos no se pierde.

- Una falla del efecto de Caja detiene el cobro; ya no queda en un campo que
  nadie lee.
- El efectivo en poder del repartidor existe en el mayor: el cobro lo traslada
  de la caja a la cuenta del repartidor y la liquidación lo lleva a caja general.
- La venta y el cobro del repartidor no cuentan dos veces el mismo dinero.
"""

from __future__ import annotations

import sqlite3
from decimal import Decimal

import pytest

from backend.application.orders_delivery.authorization import OrdersDeliveryAuthorizationPolicy
from backend.application.orders_delivery.use_cases.cash_collection_use_cases import (
    CreateCashCollectionRequestUseCase,
    RecordCashCollectionUseCase,
)
from backend.application.orders_delivery.use_cases.delivery_job_use_cases import (
    AssignDriverUseCase,
    CreateDeliveryJobUseCase,
)
from backend.application.orders_delivery.use_cases.inventory_use_cases import (
    ReserveOrderInventoryUseCase,
)
from backend.application.orders_delivery.use_cases.order_capture_use_cases import (
    ConfirmCustomerOrderUseCase,
    CreateCustomerOrderUseCase,
)
from backend.application.orders_delivery.use_cases.sales_finance_use_cases import (
    ProjectOrderToSaleUseCase,
    RecordOrderPaymentUseCase,
)
from backend.application.orders_delivery.use_cases.settlement_use_cases import (
    ApproveDriverSettlementUseCase,
    CloseDriverSettlementUseCase,
    CreateDriverSettlementUseCase,
)
from backend.application.sales.authorization import (
    AllowAllSalesPermissionCheckerForTests,
    SalesAuthorizationPolicy,
)
from backend.application.services.finance.finance_bootstrap import bootstrap_finance
from backend.infrastructure.db.repositories.orders_delivery.customer_order_repository import (
    CustomerOrderRepository,
)
from backend.infrastructure.db.schema.finance_schema import create_finance_schema
from backend.infrastructure.db.schema.inventory_schema import create_inventory_schema
from backend.infrastructure.db.schema.orders_delivery_schema import create_orders_delivery_schema
from backend.infrastructure.db.schema.sales_schema import create_sales_schema
from backend.shared.events.application_bus import ApplicationEventBus
from backend.shared.ids import new_uuid
from tests.integration._audit_trail_table import create_audit_logs_table
from tests.integration._delivery_address import give_delivery_address
from tests.integration._pos_ready import create_cash_schema, open_cash_shift

CAJA_GENERAL, CAJA_POS, REPARTIDORES = "1101", "1102", "1104"
FALTANTES, SOBRANTES, VENTAS = "7501", "7120", "4101"


@pytest.fixture
def conn():
    connection = sqlite3.connect(":memory:")
    create_orders_delivery_schema(connection)
    create_audit_logs_table(connection)
    create_inventory_schema(connection)
    create_sales_schema(connection)
    create_cash_schema(connection)
    create_finance_schema(connection)
    bootstrap_finance(connection)
    connection.commit()
    yield connection
    connection.close()


def _auth() -> OrdersDeliveryAuthorizationPolicy:
    return OrdersDeliveryAuthorizationPolicy.permissive_for_tests()


def _sales_auth() -> SalesAuthorizationPolicy:
    return SalesAuthorizationPolicy(AllowAllSalesPermissionCheckerForTests())


def _stock(conn, product_id, branch_id):
    conn.execute(
        "INSERT INTO inventory_balances (id, product_id, branch_id, warehouse_id,"
        " location_id, lot_id, serial_id, inventory_status, quantity, weight,"
        " reserved_quantity, reserved_weight, version, updated_at)"
        " VALUES (?,?,?,?,?,'','','AVAILABLE','100','0','0','0',0,'t')",
        (new_uuid(), product_id, branch_id, branch_id, branch_id))


def _bus(conn) -> ApplicationEventBus:
    """El cableado real: Pedidos y Ventas hacia Finanzas."""
    from backend.application.orders_delivery.integrations.wiring import wire_orders_delivery
    from backend.application.sales.integrations.wiring import wire_sales

    bus = ApplicationEventBus()
    wire_orders_delivery(bus, conn)
    wire_sales(bus, conn)
    return bus


def _entregar_outbox(conn, bus):
    from backend.application.orders_delivery.integrations.orders_delivery_outbox_dispatcher import (
        dispatch_orders_delivery_outbox,
    )
    from backend.application.sales.integrations.wiring import dispatch_sales_outbox

    pedidos = dispatch_orders_delivery_outbox(conn, bus)
    dispatch_sales_outbox(conn, bus)
    return pedidos


def _saldo(conn, codigo) -> Decimal:
    """Saldo deudor de la cuenta en el mayor."""
    filas = conn.execute(
        "SELECT l.debit_amount, l.credit_amount FROM journal_lines l JOIN accounts a ON a.id = l.account_id"
        " WHERE a.code=?", (codigo,)).fetchall()
    return sum((Decimal(str(d or "0")) - Decimal(str(c or "0")) for d, c in filas), Decimal("0"))


def _asientos_cuadran(conn) -> None:
    filas = conn.execute("SELECT debit_amount, credit_amount FROM journal_lines").fetchall()
    assert filas, "no se generó ningún asiento"
    assert sum(Decimal(str(f[0] or "0")) for f in filas) == sum(
        Decimal(str(f[1] or "0")) for f in filas)


def _pedido(conn, *, fulfillment="COUNTER", precio="100.00"):
    branch_id, product_id = new_uuid(), new_uuid()
    _stock(conn, product_id, branch_id)
    creado = CreateCustomerOrderUseCase(_auth()).execute(
        conn, branch_id=branch_id, channel="POS", order_type="STANDARD",
        fulfillment_type=fulfillment,
        lines=[{"product_id": product_id, "unit_price": precio, "requested_quantity": "1"}],
        actor_user_id=new_uuid(), operation_id=new_uuid())
    assert creado.success, creado.message
    order_id = creado.entity_id
    if fulfillment != "COUNTER":
        give_delivery_address(conn, order_id, branch_id=branch_id, authorization=_auth())
    ConfirmCustomerOrderUseCase(_auth()).execute(
        conn, order_id=order_id, actor_user_id=new_uuid(), operation_id=new_uuid())
    ReserveOrderInventoryUseCase(_auth()).execute(
        conn, order_id=order_id, actor_user_id=new_uuid(), operation_id=new_uuid())
    return order_id, branch_id


def _proyectar(conn, order_id, cajero=None):
    cajero = cajero or new_uuid()
    resultado = ProjectOrderToSaleUseCase(_auth()).execute(
        conn, order_id=order_id, cashier_user_id=cajero, actor_user_id=new_uuid(),
        operation_id=new_uuid(), sales_authorization=_sales_auth())
    assert resultado.success, resultado.message
    return resultado.data["sale_id"], cajero


def _pagar(conn, order_id, amount="100.00", method="CASH", operation_id=None,
           reference=None):
    return RecordOrderPaymentUseCase(_auth()).execute(
        conn, order_id=order_id, method=method, amount=Decimal(amount),
        actor_user_id=new_uuid(), operation_id=operation_id or new_uuid(), reference=reference,
        sales_authorization=_sales_auth())


def _cobro_a_domicilio(conn, *, esperado="100.00", cobrado="100.00", metodo="CASH"):
    order_id, branch_id = _pedido(conn, fulfillment="HOME_DELIVERY")
    driver_id = new_uuid()
    job_id = CreateDeliveryJobUseCase(_auth()).execute(
        conn, order_id=order_id, branch_id=branch_id, actor_user_id=new_uuid(),
        operation_id=new_uuid(), cash_to_collect=Decimal(esperado),
        payment_method_expected=metodo).entity_id
    AssignDriverUseCase(_auth()).execute(
        conn, delivery_job_id=job_id, driver_id=driver_id, actor_user_id=new_uuid(),
        operation_id=new_uuid())
    cobro = CreateCashCollectionRequestUseCase(_auth()).execute(
        conn, delivery_job_id=job_id, payment_method=metodo, actor_user_id=new_uuid(),
        operation_id=new_uuid())
    assert cobro.success, cobro.message
    registrado = RecordCashCollectionUseCase(_auth()).execute(
        conn, collection_id=cobro.entity_id, collected_amount=Decimal(cobrado),
        actor_user_id=new_uuid(), operation_id=new_uuid())
    assert registrado.success, registrado.message
    return order_id, branch_id, driver_id


def _liquidar(conn, *, driver_id, branch_id):
    creada = CreateDriverSettlementUseCase(_auth()).execute(
        conn, driver_id=driver_id, branch_id=branch_id, actor_user_id=new_uuid(),
        operation_id=new_uuid())
    assert creada.success, creada.message
    settlement_id = creada.entity_id
    for _paso in range(2):
        estado = conn.execute("SELECT status FROM driver_settlements WHERE id=?",
                              (settlement_id,)).fetchone()[0]
        if estado == "APPROVED":
            break
        aprobada = ApproveDriverSettlementUseCase(_auth()).execute(
            conn, settlement_id=settlement_id, actor_user_id=new_uuid(),
            operation_id=new_uuid())
        assert aprobada.success, aprobada.message
    cerrada = CloseDriverSettlementUseCase(_auth()).execute(
        conn, settlement_id=settlement_id, actor_user_id=new_uuid(), operation_id=new_uuid())
    assert cerrada.success, cerrada.message


class TestFallaDelEfectoDeCaja:
    def test_efectivo_sin_turno_no_completa_la_venta_y_lo_dice(self, conn):
        order_id, _branch_id = _pedido(conn)
        sale_id, _cajero = _proyectar(conn, order_id)

        resultado = _pagar(conn, order_id)

        assert not resultado.success
        assert "turno" in resultado.message.lower()
        assert conn.execute("SELECT status FROM sales WHERE id=?",
                            (sale_id,)).fetchone()[0] != "COMPLETED"
        assert conn.execute(
            "SELECT payment_status FROM customer_orders WHERE id=?",
            (order_id,)).fetchone()[0] != "PAID"

    def test_al_abrir_turno_el_reintento_completa_sin_cobrar_dos_veces(self, conn):
        order_id, branch_id = _pedido(conn)
        sale_id, cajero = _proyectar(conn, order_id)
        assert not _pagar(conn, order_id).success

        open_cash_shift(conn, branch_id=branch_id, cashier_user_id=cajero)
        resultado = _pagar(conn, order_id)

        assert resultado.success, resultado.message
        pagos = conn.execute("SELECT amount FROM sale_payments WHERE sale_id=?",
                             (sale_id,)).fetchall()
        assert len(pagos) == 1
        caja = conn.execute(
            "SELECT amount FROM cash_ledger_entries WHERE reference_id=?",
            (sale_id,)).fetchall()
        assert len(caja) == 1 and Decimal(caja[0][0]) == Decimal("100")

    def test_pago_remoto_sin_efectivo_no_exige_turno(self, conn):
        """Una transferencia no entra al cajón: pedir turno la dejaría sin cobrar."""
        order_id, _branch_id = _pedido(conn)
        sale_id, _cajero = _proyectar(conn, order_id)

        # Decisión 2026-11-14: también en Pedidos la transferencia lleva referencia.
        resultado = _pagar(conn, order_id, method="TRANSFER", reference="SPEI-0001")

        assert resultado.success, resultado.message
        assert conn.execute("SELECT status FROM sales WHERE id=?",
                            (sale_id,)).fetchone()[0] == "COMPLETED"

    def test_una_transferencia_sin_referencia_se_rechaza(self, conn):
        """Decisión 2026-11-14: la misma validación de SDLC-PAY-002, desde Pedidos."""
        order_id, _branch_id = _pedido(conn)
        sale_id, _cajero = _proyectar(conn, order_id)

        resultado = _pagar(conn, order_id, method="TRANSFER")

        assert not resultado.success
        assert "referencia es obligatoria" in resultado.message
        assert conn.execute("SELECT COUNT(*) FROM sale_payments WHERE sale_id=?",
                            (sale_id,)).fetchone()[0] == 0
        assert CustomerOrderRepository(conn).get(order_id).payment_status.value != "PAID"


class TestEfectivoDelRepartidor:
    def test_el_cobro_traslada_de_caja_a_repartidor(self, conn):
        bus = _bus(conn)
        _cobro_a_domicilio(conn)

        _entregar_outbox(conn, bus)

        assert _saldo(conn, REPARTIDORES) == Decimal("100")
        assert _saldo(conn, CAJA_POS) == Decimal("-100")
        _asientos_cuadran(conn)

    def test_la_liquidacion_lleva_el_efectivo_a_caja_general(self, conn):
        bus = _bus(conn)
        _order, branch_id, driver_id = _cobro_a_domicilio(conn)

        _liquidar(conn, driver_id=driver_id, branch_id=branch_id)
        _entregar_outbox(conn, bus)

        assert _saldo(conn, REPARTIDORES) == Decimal("0")
        assert _saldo(conn, CAJA_GENERAL) == Decimal("100")
        _asientos_cuadran(conn)

    def test_sin_doble_conteo_entre_la_venta_y_el_cobro(self, conn):
        bus = _bus(conn)
        order_id, branch_id, driver_id = _cobro_a_domicilio(conn)
        sale_id, _cajero = _proyectar(conn, order_id)

        pago = _pagar(conn, order_id)

        assert pago.success, pago.message
        # El dinero lo trae el repartidor, no un cajón: Caja no lo cuenta.
        assert conn.execute("SELECT COUNT(*) FROM cash_ledger_entries WHERE reference_id=?",
                            (sale_id,)).fetchone()[0] == 0
        _liquidar(conn, driver_id=driver_id, branch_id=branch_id)
        _entregar_outbox(conn, bus)

        efectivo = sum((_saldo(conn, c) for c in (CAJA_GENERAL, CAJA_POS, REPARTIDORES)),
                       Decimal("0"))
        assert efectivo == Decimal("100"), "el mismo dinero se contó dos veces"
        assert _saldo(conn, CAJA_POS) == Decimal("0")
        assert _saldo(conn, REPARTIDORES) == Decimal("0")
        assert _saldo(conn, VENTAS) < 0
        _asientos_cuadran(conn)

    def test_faltante_en_la_liquidacion_va_a_faltantes(self, conn):
        bus = _bus(conn)
        order_id, branch_id, driver_id = _cobro_a_domicilio(conn, cobrado="90.00")
        _proyectar(conn, order_id)
        assert _pagar(conn, order_id).success

        _liquidar(conn, driver_id=driver_id, branch_id=branch_id)
        _entregar_outbox(conn, bus)

        assert _saldo(conn, CAJA_GENERAL) == Decimal("90")
        assert _saldo(conn, FALTANTES) == Decimal("10")
        assert _saldo(conn, CAJA_POS) == Decimal("0")
        assert _saldo(conn, REPARTIDORES) == Decimal("0")
        _asientos_cuadran(conn)

    def test_sobrante_en_la_liquidacion_va_a_sobrantes(self, conn):
        bus = _bus(conn)
        order_id, branch_id, driver_id = _cobro_a_domicilio(conn, cobrado="110.00")
        _proyectar(conn, order_id)
        assert _pagar(conn, order_id).success

        _liquidar(conn, driver_id=driver_id, branch_id=branch_id)
        _entregar_outbox(conn, bus)

        assert _saldo(conn, CAJA_GENERAL) == Decimal("110")
        assert _saldo(conn, SOBRANTES) == Decimal("-10")
        assert _saldo(conn, CAJA_POS) == Decimal("0")
        _asientos_cuadran(conn)

    def test_un_cobro_con_tarjeta_no_es_efectivo_en_custodia(self, conn):
        bus = _bus(conn)
        _order, branch_id, driver_id = _cobro_a_domicilio(conn, metodo="CARD_TERMINAL")

        _liquidar(conn, driver_id=driver_id, branch_id=branch_id)
        _entregar_outbox(conn, bus)

        assert _saldo(conn, REPARTIDORES) == Decimal("0")
        assert _saldo(conn, CAJA_GENERAL) == Decimal("0")

    def test_entregar_dos_veces_no_duplica_el_asiento(self, conn):
        from backend.application.event_handlers.finance.driver_cash_handlers import (
            DriverCashCollectedHandler,
        )
        import json

        bus = _bus(conn)
        _cobro_a_domicilio(conn)
        _entregar_outbox(conn, bus)
        fila = conn.execute(
            "SELECT payload_json FROM orders_delivery_outbox WHERE event_type=?",
            ("DELIVERY_CASH_COLLECTION_RECORDED",)).fetchone()

        from backend.application.orders_delivery.integrations.wiring import to_finance_payload

        sobre = to_finance_payload(json.loads(fila[0]))
        DriverCashCollectedHandler(conn).handle({**sobre, "event_id": new_uuid()})

        assert _saldo(conn, REPARTIDORES) == Decimal("100")


class TestMigracion388:
    def _modulo(self):
        import importlib
        return importlib.import_module("migrations.standalone.388_driver_cash_account")

    def test_agrega_cuenta_y_perfil_a_un_catalogo_ya_sembrado(self, conn):
        conn.execute("DELETE FROM posting_profiles WHERE profile_key='DRIVER_CASH'")
        conn.execute("DELETE FROM accounts WHERE code='1104'")
        conn.commit()

        self._modulo().run(conn)
        self._modulo().run(conn)   # idempotente

        cuenta = conn.execute("SELECT id, account_type, normal_balance FROM accounts"
                              " WHERE code='1104'").fetchall()
        assert len(cuenta) == 1 and cuenta[0][1:] == ("ASSET", "DEBIT")
        perfiles = conn.execute("SELECT accounts_json FROM posting_profiles"
                                " WHERE profile_key='DRIVER_CASH'").fetchall()
        assert len(perfiles) == 1 and cuenta[0][0] in perfiles[0][0]

        bus = _bus(conn)
        _cobro_a_domicilio(conn)
        _entregar_outbox(conn, bus)
        assert _saldo(conn, REPARTIDORES) == Decimal("100")

    def test_sin_catalogo_no_hace_nada(self):
        vacia = sqlite3.connect(":memory:")
        create_finance_schema(vacia)

        self._modulo().run(vacia)

        assert vacia.execute("SELECT COUNT(*) FROM accounts").fetchone()[0] == 0
        vacia.close()


class TestColaDePedidos:
    def test_sin_consumidor_el_cobro_no_se_marca_entregado(self, conn):
        _cobro_a_domicilio(conn)
        bus = ApplicationEventBus()   # sin cablear

        estadistica = _entregar_outbox(conn, bus)

        assert estadistica["without_consumer"] == 1
        assert conn.execute(
            "SELECT status FROM orders_delivery_outbox WHERE event_type=?",
            ("DELIVERY_CASH_COLLECTION_RECORDED",)).fetchone()[0] == "PENDING"

    def test_si_finanzas_falla_el_evento_se_reintenta(self, conn):
        conn.execute("UPDATE posting_profiles SET active=0 WHERE profile_key='DRIVER_CASH'")
        conn.commit()
        bus = _bus(conn)
        _cobro_a_domicilio(conn)

        estadistica = _entregar_outbox(conn, bus)

        assert estadistica["failed"] == 1
        fila = conn.execute(
            "SELECT status, last_error FROM orders_delivery_outbox WHERE event_type=?",
            ("DELIVERY_CASH_COLLECTION_RECORDED",)).fetchone()
        assert fila[0] == "PENDING" and fila[1]
        assert _saldo(conn, REPARTIDORES) == Decimal("0")
