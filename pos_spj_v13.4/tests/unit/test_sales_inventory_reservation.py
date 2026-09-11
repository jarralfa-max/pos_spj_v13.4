"""SALES-9/POS-9 — reserva de inventario: reservar, cumplir, liberar, caducar.

Reescrita sobre el modelo CANÓNICO (`inventory_reservation` + los casos de uso
de `backend/application/inventory/`). La versión anterior montaba a mano las
tablas legacy `stock_reservas`/`stock_reserva_detalles` y comprobaba una cadena
de estado ('activa'/'confirmada'/'cancelada'); esas tablas y el servicio que
las movía ya no existen.

QUÉ SE COMPRUEBA AHORA, Y POR QUÉ ES MÁS FUERTE
-----------------------------------------------
El modelo legacy NO retenía disponibilidad: sólo anotaba filas. Dos cajas
podían vender la última pieza. El canónico sube `reserved_quantity` del saldo,
así que lo que hay que probar no es un estado sino el DISPONIBLE — que es lo
que impide la doble venta. Por eso aquí se afirma sobre
`InventoryBalance.available_quantity` y no sobre columnas de estado.
"""

from __future__ import annotations

import sqlite3
from decimal import Decimal

import pytest

from backend.application.inventory.authorization import (
    AllowAllInventoryPermissionCheckerForTests,
    InventoryAuthorizationPolicy,
)
from backend.application.sales.authorization import (
    AllowAllSalesPermissionCheckerForTests,
    SalesAuthorizationPolicy,
)
from backend.application.sales.use_cases.cart_use_cases import AddSaleLineUseCase, StartSaleUseCase
from backend.application.sales.use_cases.inventory_use_cases import (
    ConfirmInventoryReservationUseCase,
    ExpireOrphanedInventoryReservationsUseCase,
    ReleaseInventoryReservationUseCase,
    ReserveInventoryForSaleUseCase,
)
from backend.application.sales.use_cases.lifecycle_use_cases import (
    CancelSaleUseCase,
    SuspendSaleUseCase,
)
from backend.domain.inventory.enums import InventoryStatus, ReservationStatus
from backend.domain.inventory.exceptions import InventoryConfigurationError
from backend.domain.sales.exceptions import InventoryReservationFailedError
from backend.infrastructure.db.repositories.inventory.reservation_repository import (
    ReservationRepository,
)
from backend.infrastructure.db.repositories.inventory.unit_of_work import InventoryUnitOfWork
from backend.infrastructure.db.repositories.sales.sale_repository import SaleRepository
from backend.infrastructure.db.schema.inventory_schema import create_inventory_schema
from backend.infrastructure.db.schema.sales_schema import create_sales_schema
from backend.infrastructure.integrations.sales_inventory_client import SalesInventoryClient
from backend.shared.ids import new_uuid


def _sales_auth() -> SalesAuthorizationPolicy:
    return SalesAuthorizationPolicy(AllowAllSalesPermissionCheckerForTests())


def _inventory_auth() -> InventoryAuthorizationPolicy:
    return InventoryAuthorizationPolicy(AllowAllInventoryPermissionCheckerForTests())


@pytest.fixture
def conn():
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    create_sales_schema(c)
    create_inventory_schema(c)
    c.commit()
    yield c
    c.close()


def _seed_stock(conn, *, branch_id: str, product_id: str, quantity: str) -> None:
    """Deja existencia disponible real, por la vía canónica (el saldo)."""
    from backend.domain.inventory.entities.inventory_balance import InventoryBalance

    with InventoryUnitOfWork(conn) as uow:
        balance = InventoryBalance.empty(
            product_id=product_id, branch_id=branch_id, warehouse_id=branch_id,
            inventory_status=InventoryStatus.AVAILABLE)
        balance.apply_delta(quantity=Decimal(quantity))
        uow.balances.upsert(balance)
    conn.commit()


def _available(conn, *, branch_id: str, product_id: str) -> Decimal:
    with InventoryUnitOfWork(conn) as uow:
        balance = uow.balances.get(
            product_id=product_id, branch_id=branch_id, warehouse_id=branch_id,
            inventory_status=InventoryStatus.AVAILABLE, location_id=None, lot_id=None)
    return balance.available_quantity if balance else Decimal("0")


def _sale_with_line(conn, *, branch_id, product_id, quantity="2") -> tuple[str, str]:
    cashier = new_uuid()
    sale_id = StartSaleUseCase(_sales_auth()).execute(
        conn, branch_id=branch_id, cashier_user_id=cashier,
        operation_id=new_uuid(), actor_user_id=cashier).entity_id
    AddSaleLineUseCase(_sales_auth()).execute(
        conn, sale_id=sale_id, product_id=product_id, quantity=Decimal(quantity),
        unit_price=Decimal("10.00"), actor_user_id=cashier, operation_id=new_uuid())
    return sale_id, cashier


def _client(conn, *, branch_id, actor) -> SalesInventoryClient:
    return SalesInventoryClient(conn, branch_id=branch_id, actor_user_id=actor,
                                authorization=_inventory_auth())


def _statuses(conn, sale_id: str) -> list[ReservationStatus]:
    rows = ReservationRepository(conn)._query(
        "SELECT status FROM inventory_reservation WHERE source_document_id=?", (sale_id,))
    return [ReservationStatus(row["status"]) for row in rows]


class TestSalesInventoryClient:
    def test_reserving_reduces_what_is_available_to_sell(self, conn):
        """Lo que el modelo legacy NO hacía: retener de verdad."""
        branch_id, product_id = new_uuid(), new_uuid()
        _seed_stock(conn, branch_id=branch_id, product_id=product_id, quantity="10")
        sale_id, cashier = _sale_with_line(conn, branch_id=branch_id, product_id=product_id)
        sale = SaleRepository(conn).get(sale_id)

        assert _available(conn, branch_id=branch_id, product_id=product_id) == Decimal("10")
        handle = _client(conn, branch_id=branch_id, actor=cashier).reserve_for_sale(sale)
        conn.commit()

        assert handle == sale_id
        assert _available(conn, branch_id=branch_id, product_id=product_id) == Decimal("8")

    def test_reserve_is_idempotent_and_does_not_double_hold(self, conn):
        """Reintentar no debe retener el doble: `operation_id` es determinista."""
        branch_id, product_id = new_uuid(), new_uuid()
        _seed_stock(conn, branch_id=branch_id, product_id=product_id, quantity="10")
        sale_id, cashier = _sale_with_line(conn, branch_id=branch_id, product_id=product_id)
        sale = SaleRepository(conn).get(sale_id)
        client = _client(conn, branch_id=branch_id, actor=cashier)

        client.reserve_for_sale(sale)
        client.reserve_for_sale(sale)
        conn.commit()

        assert _available(conn, branch_id=branch_id, product_id=product_id) == Decimal("8")

    def test_reserve_without_enough_stock_fails(self, conn):
        branch_id, product_id = new_uuid(), new_uuid()
        _seed_stock(conn, branch_id=branch_id, product_id=product_id, quantity="1")
        sale_id, cashier = _sale_with_line(
            conn, branch_id=branch_id, product_id=product_id, quantity="5")
        sale = SaleRepository(conn).get(sale_id)

        with pytest.raises(InventoryReservationFailedError):
            _client(conn, branch_id=branch_id, actor=cashier).reserve_for_sale(sale)

    def test_a_failed_reservation_leaves_nothing_held(self, conn):
        """Una venta no puede quedarse reteniendo media compra.

        Dos productos: del primero hay de sobra, del segundo no. Al fallar el
        segundo, la retención del primero tiene que deshacerse.
        """
        branch_id, cashier = new_uuid(), new_uuid()
        abundante, escaso = new_uuid(), new_uuid()
        _seed_stock(conn, branch_id=branch_id, product_id=abundante, quantity="10")
        _seed_stock(conn, branch_id=branch_id, product_id=escaso, quantity="1")

        sale_id = StartSaleUseCase(_sales_auth()).execute(
            conn, branch_id=branch_id, cashier_user_id=cashier,
            operation_id=new_uuid(), actor_user_id=cashier).entity_id
        for product_id, cantidad in ((abundante, "2"), (escaso, "5")):
            AddSaleLineUseCase(_sales_auth()).execute(
                conn, sale_id=sale_id, product_id=product_id, quantity=Decimal(cantidad),
                unit_price=Decimal("10.00"), actor_user_id=cashier, operation_id=new_uuid())
        sale = SaleRepository(conn).get(sale_id)

        with pytest.raises(InventoryReservationFailedError):
            _client(conn, branch_id=branch_id, actor=cashier).reserve_for_sale(sale)
        conn.commit()

        assert _available(conn, branch_id=branch_id, product_id=abundante) == Decimal("10")

    def test_the_same_product_on_two_lines_is_reserved_once(self, conn):
        """Dos pesadas del mismo corte son un solo producto que reservar.

        Sin agrupar, las dos líneas generarían el mismo `operation_id` y la
        segunda chocaría contra su restricción de unicidad.
        """
        branch_id, product_id, cashier = new_uuid(), new_uuid(), new_uuid()
        _seed_stock(conn, branch_id=branch_id, product_id=product_id, quantity="10")
        sale_id = StartSaleUseCase(_sales_auth()).execute(
            conn, branch_id=branch_id, cashier_user_id=cashier,
            operation_id=new_uuid(), actor_user_id=cashier).entity_id
        for cantidad in ("2", "3"):
            AddSaleLineUseCase(_sales_auth()).execute(
                conn, sale_id=sale_id, product_id=product_id, quantity=Decimal(cantidad),
                unit_price=Decimal("10.00"), actor_user_id=cashier, operation_id=new_uuid())
        sale = SaleRepository(conn).get(sale_id)

        _client(conn, branch_id=branch_id, actor=cashier).reserve_for_sale(sale)
        conn.commit()

        assert len(_statuses(conn, sale_id)) == 1
        assert _available(conn, branch_id=branch_id, product_id=product_id) == Decimal("5")

    def test_confirming_keeps_the_hold_because_the_goods_left(self, conn):
        """Cumplir NO devuelve la mercancía a disponible: se vendió.

        Soltarla haría que lo ya cobrado volviera a aparecer vendible en la
        caja. Ver `FulfillReservationUseCase` para por qué tampoco se descuenta
        la existencia aquí.
        """
        branch_id, product_id = new_uuid(), new_uuid()
        _seed_stock(conn, branch_id=branch_id, product_id=product_id, quantity="10")
        sale_id, cashier = _sale_with_line(conn, branch_id=branch_id, product_id=product_id)
        sale = SaleRepository(conn).get(sale_id)
        client = _client(conn, branch_id=branch_id, actor=cashier)
        handle = client.reserve_for_sale(sale)

        client.confirm(handle, sale_id=sale.id, folio=sale.id)
        conn.commit()

        assert _statuses(conn, sale_id) == [ReservationStatus.FULFILLED]
        assert _available(conn, branch_id=branch_id, product_id=product_id) == Decimal("8")

    def test_releasing_gives_the_stock_back(self, conn):
        branch_id, product_id = new_uuid(), new_uuid()
        _seed_stock(conn, branch_id=branch_id, product_id=product_id, quantity="10")
        sale_id, cashier = _sale_with_line(conn, branch_id=branch_id, product_id=product_id)
        sale = SaleRepository(conn).get(sale_id)
        client = _client(conn, branch_id=branch_id, actor=cashier)
        handle = client.reserve_for_sale(sale)

        client.release(handle, reason="cancelada")
        conn.commit()

        assert _statuses(conn, sale_id) == [ReservationStatus.RELEASED]
        assert _available(conn, branch_id=branch_id, product_id=product_id) == Decimal("10")

    def test_releasing_twice_is_harmless(self, conn):
        branch_id, product_id = new_uuid(), new_uuid()
        _seed_stock(conn, branch_id=branch_id, product_id=product_id, quantity="10")
        sale_id, cashier = _sale_with_line(conn, branch_id=branch_id, product_id=product_id)
        sale = SaleRepository(conn).get(sale_id)
        client = _client(conn, branch_id=branch_id, actor=cashier)
        handle = client.reserve_for_sale(sale)

        client.release(handle, reason="cancelada")
        client.release(handle, reason="cancelada")
        conn.commit()

        assert _available(conn, branch_id=branch_id, product_id=product_id) == Decimal("10")

    def test_expire_orphaned_on_an_empty_system_returns_zero(self, conn):
        assert _client(conn, branch_id=new_uuid(), actor=new_uuid()).expire_orphaned() == 0

    def test_a_client_without_authorization_raises_instead_of_granting(self, conn):
        """§23: sin política inyectada NO se concede nada.

        Y no deniega en silencio: `InventoryAuthorizationPolicy` sin verificador
        lanza un error de CONFIGURACIÓN. Es lo correcto — un cableado incompleto
        se nota al instante en vez de parecer "este usuario no tiene permiso".
        """
        branch_id, product_id = new_uuid(), new_uuid()
        _seed_stock(conn, branch_id=branch_id, product_id=product_id, quantity="10")
        sale_id, cashier = _sale_with_line(conn, branch_id=branch_id, product_id=product_id)
        sale = SaleRepository(conn).get(sale_id)

        sin_politica = SalesInventoryClient(conn, branch_id=branch_id, actor_user_id=cashier)
        with pytest.raises(InventoryConfigurationError):
            sin_politica.reserve_for_sale(sale)


class TestReservationUseCases:
    def test_reserve_use_case_is_idempotent(self, conn):
        branch_id, product_id = new_uuid(), new_uuid()
        _seed_stock(conn, branch_id=branch_id, product_id=product_id, quantity="10")
        sale_id, cashier = _sale_with_line(conn, branch_id=branch_id, product_id=product_id)
        use_case = ReserveInventoryForSaleUseCase(_sales_auth(), _inventory_auth())

        first = use_case.execute(conn, sale_id=sale_id, actor_user_id=cashier,
                                 operation_id=new_uuid())
        second = use_case.execute(conn, sale_id=sale_id, actor_user_id=cashier,
                                  operation_id=new_uuid())
        conn.commit()

        assert first.success and second.success
        assert _available(conn, branch_id=branch_id, product_id=product_id) == Decimal("8")

    def test_reserve_use_case_fails_cleanly_without_stock(self, conn):
        branch_id, product_id = new_uuid(), new_uuid()
        _seed_stock(conn, branch_id=branch_id, product_id=product_id, quantity="1")
        sale_id, cashier = _sale_with_line(
            conn, branch_id=branch_id, product_id=product_id, quantity="5")

        result = ReserveInventoryForSaleUseCase(_sales_auth(), _inventory_auth()).execute(
            conn, sale_id=sale_id, actor_user_id=cashier, operation_id=new_uuid())
        assert not result.success

    def test_confirm_use_case(self, conn):
        branch_id, product_id = new_uuid(), new_uuid()
        _seed_stock(conn, branch_id=branch_id, product_id=product_id, quantity="10")
        sale_id, cashier = _sale_with_line(conn, branch_id=branch_id, product_id=product_id)
        ReserveInventoryForSaleUseCase(_sales_auth(), _inventory_auth()).execute(
            conn, sale_id=sale_id, actor_user_id=cashier, operation_id=new_uuid())

        result = ConfirmInventoryReservationUseCase(_sales_auth(), _inventory_auth()).execute(
            conn, sale_id=sale_id, actor_user_id=cashier, operation_id=new_uuid())
        conn.commit()

        assert result.success
        assert _statuses(conn, sale_id) == [ReservationStatus.FULFILLED]

    def test_confirm_without_a_reservation_is_a_noop_ok(self, conn):
        branch_id, product_id = new_uuid(), new_uuid()
        _seed_stock(conn, branch_id=branch_id, product_id=product_id, quantity="10")
        sale_id, cashier = _sale_with_line(conn, branch_id=branch_id, product_id=product_id)

        result = ConfirmInventoryReservationUseCase(_sales_auth(), _inventory_auth()).execute(
            conn, sale_id=sale_id, actor_user_id=cashier, operation_id=new_uuid())
        assert result.success

    def test_release_use_case(self, conn):
        branch_id, product_id = new_uuid(), new_uuid()
        _seed_stock(conn, branch_id=branch_id, product_id=product_id, quantity="10")
        sale_id, cashier = _sale_with_line(conn, branch_id=branch_id, product_id=product_id)
        ReserveInventoryForSaleUseCase(_sales_auth(), _inventory_auth()).execute(
            conn, sale_id=sale_id, actor_user_id=cashier, operation_id=new_uuid())

        result = ReleaseInventoryReservationUseCase(_sales_auth(), _inventory_auth()).execute(
            conn, sale_id=sale_id, actor_user_id=cashier, operation_id=new_uuid())
        conn.commit()

        assert result.success
        assert _available(conn, branch_id=branch_id, product_id=product_id) == Decimal("10")

    def test_expire_orphaned_use_case(self, conn):
        use_case = ExpireOrphanedInventoryReservationsUseCase(_sales_auth(), _inventory_auth())
        assert use_case.execute(conn, branch_id=new_uuid()) == 0


class TestSuspendReservesInventoryForReal:
    def test_suspend_reserves_inventory(self, conn):
        branch_id, product_id = new_uuid(), new_uuid()
        _seed_stock(conn, branch_id=branch_id, product_id=product_id, quantity="10")
        sale_id, cashier = _sale_with_line(conn, branch_id=branch_id, product_id=product_id)

        result = SuspendSaleUseCase(_sales_auth(), _inventory_auth()).execute(
            conn, sale_id=sale_id, actor_user_id=cashier, operation_id=new_uuid(),
            max_suspended_sales=10)
        conn.commit()

        assert result.success
        assert _available(conn, branch_id=branch_id, product_id=product_id) == Decimal("8")

    def test_suspend_fails_when_stock_insufficient_and_does_not_suspend(self, conn):
        branch_id, product_id = new_uuid(), new_uuid()
        _seed_stock(conn, branch_id=branch_id, product_id=product_id, quantity="1")
        sale_id, cashier = _sale_with_line(
            conn, branch_id=branch_id, product_id=product_id, quantity="5")

        result = SuspendSaleUseCase(_sales_auth(), _inventory_auth()).execute(
            conn, sale_id=sale_id, actor_user_id=cashier, operation_id=new_uuid(),
            max_suspended_sales=10)
        assert not result.success


class TestCancelReleasesInventoryForReal:
    def test_cancel_releases_the_reservation(self, conn):
        branch_id, product_id = new_uuid(), new_uuid()
        _seed_stock(conn, branch_id=branch_id, product_id=product_id, quantity="10")
        sale_id, cashier = _sale_with_line(conn, branch_id=branch_id, product_id=product_id)
        SuspendSaleUseCase(_sales_auth(), _inventory_auth()).execute(
            conn, sale_id=sale_id, actor_user_id=cashier, operation_id=new_uuid(),
            max_suspended_sales=10)

        result = CancelSaleUseCase(_sales_auth(), _inventory_auth()).execute(
            conn, sale_id=sale_id, reason="cancelada", actor_user_id=cashier,
            operation_id=new_uuid())
        conn.commit()

        assert result.success
        assert _available(conn, branch_id=branch_id, product_id=product_id) == Decimal("10")
