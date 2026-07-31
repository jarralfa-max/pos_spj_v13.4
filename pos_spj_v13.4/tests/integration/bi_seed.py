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


def _ensure_kg_unit(conn) -> str:
    """Unidad canónica 'kg' compartida (units_of_measure). Idempotente."""
    row = conn.execute("SELECT id FROM units_of_measure WHERE code='KG'").fetchone()
    if row:
        return row[0]
    uid = new_uuid()
    conn.execute("INSERT INTO units_of_measure (id,code,name,dimension,active) "
                 "VALUES (?,'KG','Kilogramo','WEIGHT',1)", (uid,))
    return uid


def _ensure_category(conn, categoria) -> str | None:
    """Categoría canónica (`product_categories`). Devuelve su id (o None)."""
    if not categoria or not categoria.strip():
        return None
    norm = categoria.strip().lower()
    row = conn.execute("SELECT id FROM product_categories WHERE name_normalized=?",
                       (norm,)).fetchone()
    if row:
        return row[0]
    cid = new_uuid()
    conn.execute(
        "INSERT INTO product_categories (id,code,name,name_normalized,path) "
        "VALUES (?,?,?,?,?)",
        (cid, categoria.strip().upper()[:40], categoria.strip(), norm, f"/{cid}/"))
    return cid


def add_product(conn, nombre, categoria, costo, precio=None, branch_id=None,
                existencia=5, stock_minimo=10) -> str:
    pid = new_uuid()
    precio = precio if precio is not None else costo * 1.6
    conn.execute(
        "INSERT INTO productos (id,nombre,categoria,precio,precio_compra,existencia,"
        "stock_minimo,unidad,activo) VALUES (?,?,?,?,?,?,?,?,1)",
        (pid, nombre, categoria, precio, costo, existencia, stock_minimo, "kg"))
    # ── Maestro canónico (`products`) + catálogos: los lectores BI ya no leen la
    # tabla legacy `productos`; el nombre, estado, categoría, unidad, costo y stock
    # mínimo viven en el maestro/catálogos canónicos con la MISMA identidad (pid).
    unit_id = _ensure_kg_unit(conn)
    cat_id = _ensure_category(conn, categoria)
    conn.execute(
        "INSERT INTO products (id,code,name,name_normalized,product_type,"
        "lifecycle_status,base_unit_id,category_id,sellable,purchasable,"
        "inventory_managed) VALUES (?,?,?,?,?,?,?,?,1,1,1)",
        (pid, f"P-{pid.replace('-', '')[-12:]}", nombre, nombre.strip().lower(),
         "FINISHED_GOOD",
         "ACTIVE", unit_id, cat_id))
    # Costo promedio canónico (`product_cost`, sucursal global branch_id='').
    conn.execute(
        "INSERT INTO product_cost (id,product_id,branch_id,average_cost) "
        "VALUES (?,?,'',?)", (new_uuid(), pid, str(costo)))
    # Regla de reposición global (`inventory_replenishment_rule`) → stock mínimo.
    conn.execute(
        "INSERT INTO inventory_replenishment_rule (id,product_id,branch_id,"
        "warehouse_id,min_quantity,created_at) VALUES (?,?,'','',?,datetime('now'))",
        (new_uuid(), pid, str(stock_minimo)))
    if branch_id:
        conn.execute("INSERT INTO inventory_stock (product_id,branch_id,quantity,unit) "
                     "VALUES (?,?,?,?)", (pid, branch_id, existencia, "kg"))
        # Balance canónico (`inventory_balances`): bajo el corte de inventario (INV-27,
        # flag ON) los lectores BI toman la existencia de aquí, no de inventory_stock.
        conn.execute(
            "INSERT INTO inventory_balances (id,product_id,branch_id,warehouse_id,"
            "inventory_status,quantity,updated_at) "
            "VALUES (?,?,?,'','AVAILABLE',?,datetime('now'))",
            (new_uuid(), pid, branch_id, str(existencia)))
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
