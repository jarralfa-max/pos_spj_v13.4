"""La lectura paginada de "Todos los pedidos".

Este servicio nació de sacar el SQL que `OrdersListPresenter` ejecutaba desde
`frontend/`. Como el traslado no cambia la consulta, lo que hay que fijar es lo
que la consulta ya prometía y nadie comprobaba — empezando por el filtro de
sucursal, que es el único cuyo fallo no se ve: una rejilla sin él muestra los
pedidos de todas las sucursales y parece funcionar perfectamente.
"""
from __future__ import annotations

import sqlite3

import pytest

from backend.application.orders_delivery.queries.orders_list_query_service import (
    OrdersListQueryService,
)
from backend.infrastructure.db.schema.orders_delivery_schema import (
    create_orders_delivery_schema,
)
from backend.shared.ids import new_uuid

SUCURSAL = new_uuid()
OTRA_SUCURSAL = new_uuid()


@pytest.fixture
def conn():
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    create_orders_delivery_schema(c)
    c.commit()
    yield c
    c.close()


def _pedido(conn, *, branch_id=SUCURSAL, numero="P-001", estado="CONFIRMED",
            contacto="Ana Ruiz", telefono="5551234567", creado="2026-09-10T10:00:00",
            total="250.00"):
    order_id = new_uuid()
    conn.execute(
        "INSERT INTO customer_orders (id, branch_id, order_number, channel, order_type,"
        " fulfillment_type, status, fulfillment_status, grand_total, contact_name,"
        " contact_phone, operation_id, created_at, updated_at)"
        " VALUES (?,?,?,'POS','STANDARD','PICKUP',?,'PENDING',?,?,?,?,?,?)",
        (order_id, branch_id, numero, estado, total, contacto, telefono,
         new_uuid(), creado, creado))
    conn.commit()
    return order_id


def _servicio(conn):
    return OrdersListQueryService(conn)


# ── aislamiento por sucursal ────────────────────────────────────────────────
def test_only_the_orders_of_that_branch_come_back(conn):
    """Lo que de verdad importa: sin este filtro la rejilla se ve BIEN y
    muestra pedidos de otras sucursales. No hay error que lo delate."""
    mio = _pedido(conn, branch_id=SUCURSAL, numero="P-001")
    _pedido(conn, branch_id=OTRA_SUCURSAL, numero="P-999")

    pagina = _servicio(conn).list_for_branch(SUCURSAL)

    assert [fila.id for fila in pagina.rows] == [mio]
    assert pagina.total == 1


def test_the_total_counts_only_that_branch(conn):
    """El total alimenta la paginación: contar de más inventa páginas vacías."""
    for n in range(3):
        _pedido(conn, branch_id=OTRA_SUCURSAL, numero=f"X-{n}")
    _pedido(conn, branch_id=SUCURSAL)

    assert _servicio(conn).list_for_branch(SUCURSAL).total == 1


# ── filtros ─────────────────────────────────────────────────────────────────
def test_filtering_by_status(conn):
    _pedido(conn, numero="P-001", estado="CONFIRMED")
    _pedido(conn, numero="P-002", estado="CANCELLED")

    pagina = _servicio(conn).list_for_branch(SUCURSAL, status="CANCELLED")
    assert [fila.order_number for fila in pagina.rows] == ["P-002"]


@pytest.mark.parametrize("texto", ["P-002", "Beto", "5559"])
def test_the_search_looks_in_number_name_and_phone(conn, texto):
    """El cajero escribe lo que tiene a mano; no elige por qué campo buscar."""
    _pedido(conn, numero="P-001", contacto="Ana Ruiz", telefono="5551234567")
    _pedido(conn, numero="P-002", contacto="Beto Lara", telefono="5559999999")

    pagina = _servicio(conn).list_for_branch(SUCURSAL, query=texto)
    assert [fila.order_number for fila in pagina.rows] == ["P-002"]


def test_the_search_does_not_escape_the_branch(conn):
    """Buscar no puede ser la puerta trasera que se salte la sucursal."""
    _pedido(conn, branch_id=OTRA_SUCURSAL, numero="P-777", contacto="Ana Ruiz")
    assert _servicio(conn).list_for_branch(SUCURSAL, query="Ana").rows == []


def test_a_search_with_no_matches_is_not_an_error(conn):
    _pedido(conn)
    pagina = _servicio(conn).list_for_branch(SUCURSAL, query="no-existe")
    assert pagina.rows == [] and pagina.total == 0


# ── orden y paginación ──────────────────────────────────────────────────────
def test_the_newest_order_comes_first(conn):
    """Una lista de pedidos que empieza por el más viejo obliga a paginar hasta
    el final para ver el que acaba de entrar."""
    _pedido(conn, numero="VIEJO", creado="2026-01-01T08:00:00")
    _pedido(conn, numero="NUEVO", creado="2026-09-10T08:00:00")

    pagina = _servicio(conn).list_for_branch(SUCURSAL)
    assert [fila.order_number for fila in pagina.rows] == ["NUEVO", "VIEJO"]


def test_the_second_page_continues_where_the_first_ended(conn):
    for n in range(5):
        _pedido(conn, numero=f"P-{n}", creado=f"2026-09-0{n + 1}T08:00:00")

    servicio = _servicio(conn)
    primera = servicio.list_for_branch(SUCURSAL, page=0, page_size=2)
    segunda = servicio.list_for_branch(SUCURSAL, page=1, page_size=2)

    assert [f.order_number for f in primera.rows] == ["P-4", "P-3"]
    assert [f.order_number for f in segunda.rows] == ["P-2", "P-1"]


def test_the_total_is_the_whole_filter_not_the_page(conn):
    """Si el total fuera el de la página, la paginación diría siempre "1 de 1"
    y no habría forma de llegar al resto."""
    for n in range(5):
        _pedido(conn, numero=f"P-{n}")

    pagina = _servicio(conn).list_for_branch(SUCURSAL, page=0, page_size=2)
    assert len(pagina.rows) == 2
    assert pagina.total == 5


def test_a_page_past_the_end_is_empty_and_still_reports_the_total(conn):
    _pedido(conn)
    pagina = _servicio(conn).list_for_branch(SUCURSAL, page=9, page_size=50)
    assert pagina.rows == [] and pagina.total == 1


# ── forma de los datos ──────────────────────────────────────────────────────
def test_missing_values_arrive_as_empty_text_not_none(conn):
    """La vista da formato a lo que falta (un guion). Si llegara `None`, cada
    consumidor tendría que acordarse de comprobarlo."""
    conn.execute(
        "INSERT INTO customer_orders (id, branch_id, channel, order_type,"
        " fulfillment_type, status, operation_id, created_at, updated_at)"
        " VALUES (?,?,'POS','STANDARD','PICKUP','CONFIRMED',?,"
        " '2026-09-10T10:00:00','2026-09-10T10:00:00')",
        (new_uuid(), SUCURSAL, new_uuid()))
    conn.commit()

    fila = _servicio(conn).list_for_branch(SUCURSAL).rows[0]
    assert fila.contact_name == ""
    assert fila.order_number == ""
    assert fila.id


def test_an_empty_branch_returns_an_empty_page(conn):
    pagina = _servicio(conn).list_for_branch(new_uuid())
    assert pagina.rows == [] and pagina.total == 0
