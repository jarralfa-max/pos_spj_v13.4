"""Shared seeding helpers for BI dashboard integration tests."""
from __future__ import annotations

import sqlite3
from datetime import date, timedelta

from backend.shared.ids import new_uuid


def fresh_db() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    from migrations import engine
    engine.up(conn)
    conn.commit()
    return conn


def add_branch(conn, nombre="San Bartolo") -> str:
    bid = new_uuid()
    conn.execute("INSERT INTO sucursales (id,nombre,activa) VALUES (?,?,1)", (bid, nombre))
    return bid


def add_product(conn, nombre, categoria, costo, precio=None, branch_id=None,
                existencia=5, stock_minimo=10) -> str:
    pid = new_uuid()
    precio = precio if precio is not None else costo * 1.6
    conn.execute(
        "INSERT INTO productos (id,nombre,categoria,precio,precio_compra,existencia,"
        "stock_minimo,unidad,activo) VALUES (?,?,?,?,?,?,?,?,1)",
        (pid, nombre, categoria, precio, costo, existencia, stock_minimo, "kg"))
    if branch_id:
        conn.execute("INSERT INTO inventory_stock (product_id,branch_id,quantity,unit) "
                     "VALUES (?,?,?,?)", (pid, branch_id, existencia, "kg"))
    return pid


def add_sale(conn, branch_id, items, *, forma_pago="efectivo", cliente_id="c1",
             when: date | None = None, estado="completada") -> str:
    """items: list of (product_id, qty, unit_price, unit_cost)."""
    when = when or date.today()
    vid = new_uuid()
    total = sum(q * pu for _, q, pu, _ in items)
    conn.execute(
        "INSERT INTO ventas (id,folio,total,forma_pago,estado,fecha,sucursal_id,cliente_id) "
        "VALUES (?,?,?,?,?,?,?,?)",
        (vid, "F", total, forma_pago, estado, f"{when} 13:00:00", branch_id, cliente_id))
    for pid, q, pu, pc in items:
        conn.execute(
            "INSERT INTO detalles_venta (id,venta_id,producto_id,cantidad,precio_unitario,"
            "subtotal,costo_unitario_real) VALUES (?,?,?,?,?,?,?)",
            (new_uuid(), vid, pid, q, pu, q * pu, pc))
    return vid


def add_receivable(conn, balance, branch_id=None):
    conn.execute("INSERT INTO accounts_receivable (id,cliente_id,amount,balance,status,fecha,sucursal_id) "
                 "VALUES (?,?,?,?,?,?,?)",
                 (new_uuid(), "c1", balance, balance, "open", date.today().isoformat(), branch_id))


def add_payable(conn, balance, branch_id=None):
    conn.execute("INSERT INTO accounts_payable (id,supplier_id,amount,balance,status,fecha,sucursal_id) "
                 "VALUES (?,?,?,?,?,?,?)",
                 (new_uuid(), "s1", balance, balance, "open", date.today().isoformat(), branch_id))


def add_expense(conn, monto, when: date | None = None):
    conn.execute("INSERT INTO gastos (id,fecha,categoria,concepto,monto) VALUES (?,?,?,?,?)",
                 (new_uuid(), (when or date.today()).isoformat(), "Renta", "Local", monto))


def add_waste(conn, product_id, branch_id, cantidad, valor, when: date | None = None):
    conn.execute(
        "INSERT INTO mermas (id,producto_id,sucursal_id,cantidad,motivo,usuario,operation_id,"
        "valor_perdida,fecha) VALUES (?,?,?,?,?,?,?,?,?)",
        (new_uuid(), product_id, branch_id, cantidad, "caducidad", "sys", new_uuid(),
         valor, (when or date.today()).isoformat()))


def this_month_day(day=2) -> date:
    return date.today().replace(day=1) + timedelta(days=day - 1)
