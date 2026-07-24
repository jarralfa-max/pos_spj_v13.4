# migrations/standalone/150_pricing_backfill_from_legacy.py
"""PRC-5 — backfill de precio/costo legacy → contexto canónico Pricing/Costing.

Copia (idempotente) el precio y el costo que hoy viven dispersos en el legacy
hacia las tablas born-clean de Pricing:

    productos.precio / precio_minimo_venta|precio_minimo → product_price (lista BASE)
    productos.costo_promedio|costo / precio_compra        → product_cost
    listas_precio                                         → price_list (kind CUSTOMER)
    precios_lista                                         → product_price (por lista)
    precios_volumen                                       → volume_price (tiers)
    clientes_lista_precio                                 → customer_price_list
    branch_products.precio_local                          → product_price (branch override)

Reglas del backfill:
- **Idempotente**: re-ejecutable sin duplicar (UNIQUE code / dimensión + INSERT OR
  IGNORE + guardas de existencia para tiers de volumen).
- **Decimal-only**: los valores REAL legacy se normalizan a string Decimal; nunca se
  copia un float a una columna REAL (el esquema Pricing no tiene REAL).
- **Aditivo**: el legacy queda intacto; sus lectores siguen vivos hasta PRC-6
  (repunte) y PRC-8 (DROP diferido).
- Descuento de lista = porcentaje (semántica de `pricing_service`), se guarda tal
  cual en `price_list.discount_pct`.
- Se omiten valores no significativos (precio/costo <= 0).
"""

from __future__ import annotations

import logging
from decimal import Decimal, InvalidOperation

from backend.infrastructure.db.schema.pricing_schema import create_pricing_schema
from backend.shared.ids import new_uuid

logger = logging.getLogger("spj.migrations.150")

_CUR = "MXN"


def run(conn) -> None:
    create_pricing_schema(conn)  # idempotente; garantiza destino

    base_list_id = _ensure_base_list(conn)
    stats = {
        "base_price": _backfill_base_prices(conn, base_list_id),
        "cost": _backfill_costs(conn),
        "lists": _backfill_price_lists(conn),
        "list_price": _backfill_list_prices(conn),
        "volume": _backfill_volume_prices(conn),
        "customer": _backfill_customer_lists(conn),
        "branch_price": _backfill_branch_prices(conn, base_list_id),
    }
    conn.commit()
    logger.info("150: backfill Pricing %s", stats)


# ── helpers ────────────────────────────────────────────────────────────────
def _table_exists(conn, name: str) -> bool:
    return conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,)
    ).fetchone() is not None


def _cols(conn, table: str) -> set[str]:
    return {r[1] for r in conn.execute(f"PRAGMA table_info({table})").fetchall()}


def _dec(value) -> Decimal | None:
    """REAL/str legacy → Decimal (quantizado a 0.0001, como Money); None si no aplica."""
    if value is None:
        return None
    try:
        d = Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None
    return d.quantize(Decimal("0.0001"))


def _pos(value) -> Decimal | None:
    d = _dec(value)
    return d if d is not None and d > 0 else None


# ── BASE list ──────────────────────────────────────────────────────────────
def _ensure_base_list(conn) -> str:
    row = conn.execute("SELECT id FROM price_list WHERE code='BASE'").fetchone()
    if row:
        return row[0]
    new_id = new_uuid()
    conn.execute(
        "INSERT OR IGNORE INTO price_list (id, code, name, kind, status, discount_pct) "
        "VALUES (?, 'BASE', 'Lista base', 'BASE', 'ACTIVE', '0')",
        (new_id,),
    )
    return conn.execute("SELECT id FROM price_list WHERE code='BASE'").fetchone()[0]


# ── productos.precio → product_price (BASE) ────────────────────────────────
def _backfill_base_prices(conn, base_list_id: str) -> int:
    if not _table_exists(conn, "productos"):
        return 0
    cols = _cols(conn, "productos")
    if "precio" not in cols:
        return 0
    min_expr = "0"
    if "precio_minimo_venta" in cols and "precio_minimo" in cols:
        min_expr = "COALESCE(NULLIF(precio_minimo_venta,0), precio_minimo, 0)"
    elif "precio_minimo_venta" in cols:
        min_expr = "COALESCE(precio_minimo_venta, 0)"
    elif "precio_minimo" in cols:
        min_expr = "COALESCE(precio_minimo, 0)"
    rows = conn.execute(
        f"SELECT id, precio, {min_expr} AS pmin FROM productos WHERE precio IS NOT NULL"
    ).fetchall()
    n = 0
    for pid, precio, pmin in rows:
        sale = _pos(precio)
        if sale is None:
            continue
        mn = _pos(pmin)
        n += _insert_price(
            conn, base_list_id, pid, "", sale, mn)
    return n


def _insert_price(conn, list_id, product_id, branch_id, sale: Decimal, mn: Decimal | None) -> int:
    cur = conn.execute(
        """INSERT OR IGNORE INTO product_price
             (id, price_list_id, product_id, branch_id, sale_price, sale_price_currency,
              min_price, min_price_currency)
           VALUES (?,?,?,?,?,?,?,?)""",
        (new_uuid(), list_id, product_id, branch_id, str(sale), _CUR,
         None if mn is None else str(mn), None if mn is None else _CUR),
    )
    return cur.rowcount or 0


# ── productos.costo* → product_cost ────────────────────────────────────────
def _backfill_costs(conn) -> int:
    if not _table_exists(conn, "productos"):
        return 0
    cols = _cols(conn, "productos")
    avg_candidates = [c for c in ("costo_promedio", "costo") if c in cols]
    last_col = "precio_compra" if "precio_compra" in cols else None
    if not avg_candidates and not last_col:
        return 0
    select_cols = ["id"] + avg_candidates + ([last_col] if last_col else [])
    rows = conn.execute(f"SELECT {', '.join(select_cols)} FROM productos").fetchall()
    n = 0
    for r in rows:
        d = dict(zip(select_cols, r))
        avg = next((_pos(d[c]) for c in avg_candidates if _pos(d[c]) is not None), None)
        last = _pos(d[last_col]) if last_col else None
        # sin costo promedio pero con costo de compra → úsalo como promedio inicial
        if avg is None:
            avg = last
        if avg is None:
            continue
        cur = conn.execute(
            """INSERT OR IGNORE INTO product_cost
                 (id, product_id, branch_id, average_cost, average_cost_currency,
                  last_cost, cost_method)
               VALUES (?,?,?,?,?,?, 'AVERAGE')""",
            (new_uuid(), d["id"], "", str(avg), _CUR,
             None if last is None else str(last)),
        )
        n += cur.rowcount or 0
    return n


# ── listas_precio → price_list (CUSTOMER) ──────────────────────────────────
def _backfill_price_lists(conn) -> int:
    if not _table_exists(conn, "listas_precio"):
        return 0
    cols = _cols(conn, "listas_precio")
    has_disc = "descuento_global" in cols
    has_activa = "activa" in cols
    has_nombre = "nombre" in cols
    select = ["id",
              "nombre" if has_nombre else "id AS nombre",
              "descuento_global" if has_disc else "0 AS descuento_global",
              "activa" if has_activa else "1 AS activa"]
    rows = conn.execute(f"SELECT {', '.join(select)} FROM listas_precio").fetchall()
    n = 0
    for lid, nombre, descuento_global, activa in rows:
        code = "LST-" + str(lid).replace("-", "")[:12].upper()
        name = (nombre if has_nombre and nombre else None) or f"Lista {str(lid)[:8]}"
        discount = _dec(descuento_global)
        discount = discount if discount and discount > 0 else Decimal("0")
        status = "INACTIVE" if int(activa or 0) == 0 else "ACTIVE"
        cur = conn.execute(
            """INSERT OR IGNORE INTO price_list
                 (id, code, name, kind, status, discount_pct)
               VALUES (?,?,?, 'CUSTOMER', ?, ?)""",
            (lid, code, name, status, str(discount)),
        )
        n += cur.rowcount or 0
    return n


# ── precios_lista → product_price (por lista) ──────────────────────────────
def _backfill_list_prices(conn) -> int:
    if not _table_exists(conn, "precios_lista"):
        return 0
    # solo listas que existen en el destino canónico
    rows = conn.execute(
        """SELECT pl.lista_id, pl.producto_id, pl.precio
             FROM precios_lista pl
             JOIN price_list dst ON dst.id = pl.lista_id"""
    ).fetchall()
    n = 0
    for lista_id, producto_id, precio in rows:
        sale = _pos(precio)
        if sale is None:
            continue
        n += _insert_price(conn, lista_id, producto_id, "", sale, None)
    return n


# ── precios_volumen → volume_price (tiers) ─────────────────────────────────
def _backfill_volume_prices(conn) -> int:
    if not _table_exists(conn, "precios_volumen"):
        return 0
    rows = conn.execute(
        "SELECT producto_id, lista_id, cantidad_min, precio FROM precios_volumen"
    ).fetchall()
    n = 0
    for producto_id, lista_id, cantidad_min, precio in rows:
        qty = _pos(cantidad_min)
        price = _pos(precio)
        if qty is None or price is None:
            continue
        pp = conn.execute(
            "SELECT id FROM product_price WHERE price_list_id=? AND product_id=? "
            "AND branch_id=''", (lista_id, producto_id)).fetchone()
        if pp is None:
            continue
        pp_id = pp[0]
        exists = conn.execute(
            "SELECT 1 FROM volume_price WHERE product_price_id=? AND min_quantity=? "
            "AND price=?", (pp_id, str(qty), str(price))).fetchone()
        if exists:
            continue
        conn.execute(
            "INSERT INTO volume_price (id, product_price_id, min_quantity, price, "
            "price_currency) VALUES (?,?,?,?,?)",
            (new_uuid(), pp_id, str(qty), str(price), _CUR))
        n += 1
    return n


# ── clientes_lista_precio → customer_price_list ────────────────────────────
def _backfill_customer_lists(conn) -> int:
    if not _table_exists(conn, "clientes_lista_precio"):
        return 0
    rows = conn.execute(
        """SELECT clp.cliente_id, clp.lista_id
             FROM clientes_lista_precio clp
             JOIN price_list dst ON dst.id = clp.lista_id
            WHERE clp.lista_id IS NOT NULL"""
    ).fetchall()
    n = 0
    for cliente_id, lista_id in rows:
        cur = conn.execute(
            "INSERT OR IGNORE INTO customer_price_list (customer_id, price_list_id) "
            "VALUES (?,?)", (cliente_id, lista_id))
        n += cur.rowcount or 0
    return n


# ── branch_products.precio_local → product_price (override sucursal) ───────
def _backfill_branch_prices(conn, base_list_id: str) -> int:
    if not _table_exists(conn, "branch_products"):
        return 0
    cols = _cols(conn, "branch_products")
    if "precio_local" not in cols or "branch_id" not in cols or "producto_id" not in cols:
        return 0
    rows = conn.execute(
        "SELECT branch_id, producto_id, precio_local FROM branch_products "
        "WHERE precio_local IS NOT NULL").fetchall()
    n = 0
    for branch_id, producto_id, precio_local in rows:
        sale = _pos(precio_local)
        if sale is None or not branch_id:
            continue
        n += _insert_price(conn, base_list_id, producto_id, branch_id, sale, None)
    return n


up = run
