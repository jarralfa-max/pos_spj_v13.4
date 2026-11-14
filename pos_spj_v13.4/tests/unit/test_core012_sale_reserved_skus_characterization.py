"""CARACTERIZACIÓN (SDLC-CORE-012): la venta descuenta lo RESERVADO, tal como hoy.

`SalesInventoryClient.confirm` sale de las reservas activas, no de `sale.lines`.
Fija ese contrato antes de que SDLC-SALES-001 y compañía toquen el cobro. No afirma
que sea correcto: en particular, una línea agregada tras reservar no se descuenta.
"""
from __future__ import annotations

from decimal import Decimal

from backend.application.sales.use_cases.cart_use_cases import AddSaleLineUseCase
from backend.infrastructure.db.repositories.sales.sale_repository import SaleRepository
from backend.shared.ids import new_uuid
from tests.unit.test_sales_inventory_reservation import (  # noqa: F401 - `conn` es fixture
    _client,
    _on_hand,
    _sale_with_line,
    _sales_auth,
    _seed_stock,
    conn,
)


def _productos_descontados(conn, sale_id: str) -> list[str]:
    return [str(fila[0]) for fila in conn.execute(
        "SELECT l.product_id FROM inventory_ledger m"
        " JOIN inventory_ledger_lines l ON l.movement_id = m.id"
        " WHERE m.source_document_id = ? AND m.movement_type = 'SALE_ISSUE'", (sale_id,))]


def test_a_sale_consumes_only_the_reserved_sku(conn):
    """CARACTERIZACIÓN — la conserva SDLC-SALES-001: sólo toca el precio."""
    sucursal, vendido, ajeno = new_uuid(), new_uuid(), new_uuid()
    _seed_stock(conn, branch_id=sucursal, product_id=vendido, quantity="10")
    _seed_stock(conn, branch_id=sucursal, product_id=ajeno, quantity="10")
    sale_id, cajero = _sale_with_line(conn, branch_id=sucursal, product_id=vendido)
    venta = SaleRepository(conn).get(sale_id)
    cliente = _client(conn, branch_id=sucursal, actor=cajero)

    cliente.confirm(cliente.reserve_for_sale(venta), sale_id=venta.id, folio=venta.id)
    conn.commit()

    assert _productos_descontados(conn, sale_id) == [vendido]
    assert _on_hand(conn, branch_id=sucursal, product_id=vendido) == Decimal("8")
    assert _on_hand(conn, branch_id=sucursal, product_id=ajeno) == Decimal("10")


def test_a_line_added_after_reserving_is_not_consumed(conn):
    """CARACTERIZACIÓN (defecto potencial, sin ítem asignado): lo descontado sale de
    las reservas; una línea que no llegó a reservarse no toca el inventario aquí."""
    sucursal, reservado, tardio = new_uuid(), new_uuid(), new_uuid()
    _seed_stock(conn, branch_id=sucursal, product_id=reservado, quantity="10")
    _seed_stock(conn, branch_id=sucursal, product_id=tardio, quantity="10")
    sale_id, cajero = _sale_with_line(conn, branch_id=sucursal, product_id=reservado)
    cliente = _client(conn, branch_id=sucursal, actor=cajero)
    asa = cliente.reserve_for_sale(SaleRepository(conn).get(sale_id))
    AddSaleLineUseCase(_sales_auth()).execute(
        conn, sale_id=sale_id, product_id=tardio, quantity=Decimal("3"),
        unit_price=Decimal("10.00"), actor_user_id=cajero, operation_id=new_uuid())

    cliente.confirm(asa, sale_id=sale_id, folio=sale_id)
    conn.commit()

    assert _productos_descontados(conn, sale_id) == [reservado]
    assert _on_hand(conn, branch_id=sucursal, product_id=tardio) == Decimal("10")


def test_confirming_without_a_reservation_consumes_nothing(conn):
    """CARACTERIZACIÓN: `confirm` sin reservas activas regresa sin descontar ni avisar."""
    sucursal, producto = new_uuid(), new_uuid()
    _seed_stock(conn, branch_id=sucursal, product_id=producto, quantity="10")
    sale_id, cajero = _sale_with_line(conn, branch_id=sucursal, product_id=producto)

    _client(conn, branch_id=sucursal, actor=cajero).confirm("", sale_id=sale_id, folio=sale_id)
    conn.commit()

    assert _productos_descontados(conn, sale_id) == []
    assert _on_hand(conn, branch_id=sucursal, product_id=producto) == Decimal("10")
