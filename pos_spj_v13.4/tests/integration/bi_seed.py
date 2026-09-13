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
    """Una pérdida canónica: su caso y su línea.

    Escribía en `mermas`, tabla LEGACY que `fresh_db()` ni siquiera crea,
    mientras `BiInventoryQueryService` ya leía la canónica `loss_cases`: el
    ayudante se quedó atrás cuando la consulta se repuntó, y dejaba en ERROR
    todo test de la sección Merma —reventaba en la fixture, antes de afirmar
    nada—.

    Se siembra también `loss_lines`, que `_sembrar_merma` de
    `test_bi_sucursales_precios_sections.py` no tenía: `waste_value()` suma
    sobre el CASO, pero `waste_by_category()` agrupa por categoría del producto
    uniendo `loss_lines`. Sin línea, el KPI salía bien y la gráfica vacía.
    """
    fecha = (when or date.today()).isoformat()
    # `classification_id`/`reason_id` apuntan a catálogos que las migraciones ya
    # traen sembrados (28 razones). Inventar UUIDs ahí da FOREIGN KEY failed, así
    # que se toma una pareja real.
    motivo, clasificacion = conn.execute(
        "SELECT id, classification_id FROM loss_reasons LIMIT 1").fetchone()
    caso = new_uuid()
    # La tabla impone `net_loss_value = gross_value - recoverable_value`. Es una
    # invariante real y se respeta en vez de rodearla: nada recuperable, así que
    # bruto y neto coinciden.
    conn.execute(
        "INSERT INTO loss_cases (id, operation_id, branch_id, warehouse_id,"
        " reported_by_user_id, classification_id, reason_id, origin, status,"
        " requires_inventory_posting, gross_value, recoverable_value,"
        " net_loss_value, occurred_at, created_at, updated_at)"
        " VALUES (?,?,?,?,?,?,?,'MANUAL_AUTHORIZED','APPROVED',0,?,0,?,?,?,?)",
        (caso, new_uuid(), branch_id, new_uuid(), new_uuid(), clasificacion,
         motivo, valor, valor, fecha, fecha, fecha))
    conn.execute(
        "INSERT INTO loss_lines (id, loss_case_id, product_id, quantity, unit,"
        " gross_value, recoverable_value, net_loss_value, created_at)"
        " VALUES (?,?,?,?,'kg',?,0,?,?)",
        (new_uuid(), caso, product_id, cantidad, valor, valor, fecha))


def this_month_day(day=2) -> date:
    return date.today().replace(day=1) + timedelta(days=day - 1)


# -- Caja canónica ----------------------------------------------------------
# `movimientos_caja` y `cierres_caja` NO EXISTEN: el contexto de Caja se
# reconstruyó con nombres canónicos en inglés. Sembrar ahí era lo que dejaba
# rojos los tests de la sección Caja. Las claves foráneas están ACTIVAS en
# `fresh_db()`, así que un turno exige caja registradora, cajón y terminal, y un
# corte Z exige además un conteo confirmado: la cadena se siembra entera porque
# es la única forma de que estos datos se parezcan a los que el dominio escribe.


def open_cash_shift(conn, branch_id, *, cashier_user_id=None, when: date | None = None):
    """Turno de caja abierto, con su registradora, cajón y terminal."""
    reg, drawer, term = new_uuid(), new_uuid(), new_uuid()
    shift = new_uuid()
    cajero = cashier_user_id or new_uuid()
    # Sufijo desde la COLA del uuid: en UUIDv7 la cabeza es la marca de tiempo,
    # así que dos generados en el mismo milisegundo chocarían con el índice
    # único (branch_id, name).
    sufijo = reg[-12:]
    ts = f"{(when or date.today()).isoformat()}T08:00:00+00:00"
    conn.execute("INSERT INTO cash_registers (id,branch_id,name,status,created_at,"
                 "updated_at) VALUES (?,?,?,'ACTIVE',?,?)",
                 (reg, branch_id, f"Caja {sufijo}", ts, ts))
    conn.execute("INSERT INTO cash_drawers (id,branch_id,register_id,name,status,"
                 "created_at,updated_at) VALUES (?,?,?,?,'ACTIVE',?,?)",
                 (drawer, branch_id, reg, f"Cajon {sufijo}", ts, ts))
    conn.execute("INSERT INTO pos_terminals (id,branch_id,register_id,name,status,"
                 "created_at,updated_at) VALUES (?,?,?,?,'ACTIVE',?,?)",
                 (term, branch_id, reg, f"Terminal {sufijo}", ts, ts))
    conn.execute(
        "INSERT INTO cash_shifts (id,branch_id,register_id,drawer_id,terminal_id,"
        "cashier_user_id,opening_amount,opening_operation_id,status,opened_at)"
        " VALUES (?,?,?,?,?,?,?,?,'OPEN',?)",
        (shift, branch_id, reg, drawer, term, cajero, "0", new_uuid(), ts))
    return shift


def add_cash_movement(conn, shift_id, branch_id, monto, *, direction="INFLOW",
                      movement_type=None, when: date | None = None):
    """Asiento del libro de caja. El tipo por defecto respeta el CHECK que liga
    `movement_type` con `direction`."""
    if movement_type is None:
        movement_type = "MANUAL_INCOME" if direction == "INFLOW" else "MANUAL_WITHDRAWAL"
    conn.execute(
        "INSERT INTO cash_ledger_entries (id,shift_id,branch_id,movement_type,"
        "direction,amount,operation_id,recorded_by,concept,recorded_at)"
        " VALUES (?,?,?,?,?,?,?,?,?,?)",
        (new_uuid(), shift_id, branch_id, movement_type, direction, str(monto),
         new_uuid(), new_uuid(), "seed",
         f"{(when or date.today()).isoformat()}T10:00:00+00:00"))


def add_cash_cut(conn, shift_id, branch_id, *, esperado="0", contado="0",
                 diferencia="0", when: date | None = None):
    """Corte Z (cierre). Los X son lecturas intermedias y el tablero no los
    cuenta, así que aquí sólo se siembra el que sí significa un cierre."""
    fecha = (when or date.today()).isoformat()
    usuario = new_uuid()
    conteo = new_uuid()
    conn.execute(
        "INSERT INTO cash_counts (id,shift_id,branch_id,counter_user_id,"
        "operation_id,total_counted,status,confirmed_at)"
        " VALUES (?,?,?,?,?,?,'CONFIRMED',?)",
        (conteo, shift_id, branch_id, usuario, new_uuid(), contado,
         f"{fecha}T21:55:00+00:00"))
    conn.execute(
        "INSERT INTO cash_cuts (id,shift_id,branch_id,cut_type,document_number,"
        "generated_by,expected_cash,counted_cash,difference,blind_count_id,"
        "operation_id,is_final,generated_at) VALUES (?,?,?,'Z',?,?,?,?,?,?,?,1,?)",
        (new_uuid(), shift_id, branch_id, f"DOC-{conteo[-8:]}", usuario,
         esperado, contado, diferencia, conteo, new_uuid(),
         f"{fecha}T22:00:00+00:00"))
