"""Catálogo de productos para WhatsApp leído del maestro canónico (PROD-22).

Antes el bridge, el `ProductMatcher` y la confirmación de pedido leían la tabla
legacy `productos` (+ `branch_inventory`). En la base real esas tablas están
VACÍAS — los productos viven en `products` desde el corte de Productos —, así
que el menú de WhatsApp no encontraba ningún producto. Este módulo es la única
consulta de catálogo del microservicio y usa el mismo criterio que el POS
(`SalesCatalogQueryService`):

* producto ACTIVO, vendible y no interno;
* precio de la lista BASE **activa**, el de la sucursal si rige y si no el de
  todas, sólo vigente hoy;
* existencia disponible = `inventory_balances` AVAILABLE − reservado, por sucursal.

Devuelve las mismas columnas que el código del flujo ya consume (`id`,
`nombre`, `precio`, `stock`, `unidad`, `categoria`), así que los flujos
conversacionales no cambian.
"""

from __future__ import annotations

from datetime import date

_ACTIVE_BASE_LIST = ("SELECT id FROM price_list WHERE kind = 'BASE' AND status = 'ACTIVE' "
                     "ORDER BY updated_at DESC LIMIT 1")


def _vigente(alias: str) -> str:
    return (f"({alias}.effective_from IS NULL OR {alias}.effective_from = '' "
            f"OR substr({alias}.effective_from, 1, 10) <= :today) "
            f"AND ({alias}.effective_to IS NULL OR {alias}.effective_to = '' "
            f"OR substr({alias}.effective_to, 1, 10) >= :today)")


CATALOG_SELECT = f"""
    SELECT
        p.id AS id,
        p.name AS nombre,
        COALESCE(ppb.sale_price, pp.sale_price, '0') AS precio,
        COALESCE(inv.qty, 0) AS stock,
        COALESCE(u.code, 'kg') AS unidad,
        COALESCE(pc.name, '') AS categoria
    FROM products p
    LEFT JOIN product_price ppb
        ON ppb.product_id = p.id AND ppb.branch_id = :branch AND ppb.branch_id <> ''
       AND ppb.price_list_id = ({_ACTIVE_BASE_LIST}) AND {_vigente("ppb")}
    LEFT JOIN product_price pp
        ON pp.product_id = p.id AND pp.branch_id = ''
       AND pp.price_list_id = ({_ACTIVE_BASE_LIST}) AND {_vigente("pp")}
    LEFT JOIN units_of_measure u ON u.id = p.base_unit_id
    LEFT JOIN product_categories pc ON pc.id = p.category_id
    LEFT JOIN (
        SELECT product_id, branch_id,
               printf('%.4f', SUM(CAST(quantity AS REAL)
                                  - CAST(COALESCE(reserved_quantity, 0) AS REAL))) AS qty
        FROM inventory_balances
        WHERE inventory_status = 'AVAILABLE'
        GROUP BY product_id, branch_id
    ) inv ON inv.product_id = p.id AND inv.branch_id = :branch
"""

#: Precio y existencia salen como TEXTO (Decimal en Python vía `catalog_row`).
#: SQLite sólo suma en doble precisión: el total se redondea a 4 decimales en
#: texto (las cantidades se guardan con <= 4), así no llega ningún float.

#: Lo que se puede ofrecer por WhatsApp.
OFFERABLE = ("p.lifecycle_status = 'ACTIVE' AND COALESCE(p.sellable, 0) = 1 "
             "AND COALESCE(p.internal_only, 0) = 0")


def catalog_params(branch_id, **extra) -> dict:
    return {"branch": str(branch_id or ""), "today": date.today().isoformat(), **extra}


def product_category_name(db, product_id) -> str:
    """Nombre de la categoría canónica del producto ('' si no tiene)."""
    row = db.execute(
        "SELECT COALESCE(pc.name, '') FROM products p "
        "LEFT JOIN product_categories pc ON pc.id = p.category_id WHERE p.id = ?",
        (product_id,)).fetchone()
    return (row[0] or "") if row else ""


def catalog_row(row) -> dict:
    """Fila de `CATALOG_SELECT` → dict con `precio`/`stock` como Decimal."""
    try:
        from domain.money import to_decimal
    except ImportError:  # importado como paquete `whatsapp_service.`
        from whatsapp_service.domain.money import to_decimal
    data = dict(row)
    data["precio"] = to_decimal(data.get("precio"))
    data["stock"] = to_decimal(data.get("stock"))
    return data
