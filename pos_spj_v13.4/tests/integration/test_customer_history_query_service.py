"""CustomerHistoryQueryService: historial de compras/puntos/crédito sin SQL en UI."""
from __future__ import annotations

from backend.application.queries.customer_history_query_service import (
    CustomerHistoryQueryService,
)
from backend.shared.ids import new_uuid
from tests.integration._born_clean_db import make_db


def _seed(conn):
    cid = new_uuid()
    conn.execute(
        "INSERT INTO clientes (id, nombre, activo) VALUES (?, 'Cliente H', 1)", (cid,)
    )
    venta_id = new_uuid()
    conn.execute(
        "INSERT INTO ventas (id, folio, cliente_id, total, forma_pago, loyalty_points, estado) "
        "VALUES (?, 'F-1', ?, 320.5, 'Tarjeta', 32, 'completada')",
        (venta_id, cid),
    )
    conn.execute(
        "INSERT INTO historico_puntos (id, cliente_id, tipo, puntos, saldo_actual, descripcion) "
        "VALUES (?, ?, 'venta', 32, 32, 'Compra F-1')",
        (new_uuid(), cid),
    )
    conn.execute(
        "INSERT INTO cuentas_por_cobrar (id, cliente_id, venta_id, folio, monto_original, "
        " saldo_pendiente, estado) VALUES (?, ?, ?, 'F-1', 320.5, 320.5, 'pendiente')",
        (new_uuid(), cid, venta_id),
    )
    return cid


def test_purchase_history_uses_forma_pago():
    conn = make_db()
    cid = _seed(conn)
    qs = CustomerHistoryQueryService(conn)
    compras = qs.get_purchase_history(cid)
    assert len(compras) == 1
    assert compras[0]["forma_pago"] == "Tarjeta"
    assert compras[0]["total"] == 320.5
    assert compras[0]["puntos_ganados"] == 32


def test_points_history_uses_cliente_id():
    conn = make_db()
    cid = _seed(conn)
    qs = CustomerHistoryQueryService(conn)
    puntos = qs.get_points_history(cid)
    assert len(puntos) == 1
    assert puntos[0]["puntos"] == 32
    assert puntos[0]["descripcion"] == "Compra F-1"


def test_credit_history_falls_back_to_cxc():
    conn = make_db()
    cid = _seed(conn)
    qs = CustomerHistoryQueryService(conn)
    creditos = qs.get_credit_history(cid)
    assert len(creditos) == 1
    assert creditos[0]["monto"] == 320.5


def test_missing_optional_tables_return_empty_lists():
    import sqlite3

    empty = sqlite3.connect(":memory:")
    qs = CustomerHistoryQueryService(empty)
    assert qs.get_purchase_history(new_uuid()) == []
    assert qs.get_points_history(new_uuid()) == []
    assert qs.get_credit_history(new_uuid()) == []


def test_blank_customer_id_returns_empty():
    conn = make_db()
    qs = CustomerHistoryQueryService(conn)
    assert qs.get_purchase_history("") == []
    assert qs.get_points_history(None) == []
