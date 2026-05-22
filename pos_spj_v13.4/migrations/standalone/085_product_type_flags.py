# migrations/standalone/085_product_type_flags.py — SPJ ERP FASE 2
"""
Normalización de tipo_producto y flags de receta.

Nuevas columnas en productos:
  permite_receta                 — puede tener receta definida
  permite_stock_virtual          — su stock se puede cubrir con subproductos
  descuenta_componentes_en_venta — al vender, explotar BOM y descontar componentes
  es_vendible                    — puede aparecer en punto de venta
  es_inventariable               — lleva control de existencia

Backfill desde flags legacy (es_compuesto, es_subproducto) y
desde recetas activas existentes para no perder datos.
"""


def run(conn):
    conn.executescript("""
        -- Nuevas columnas de clasificación de receta / inventario
        ALTER TABLE productos ADD COLUMN permite_receta INTEGER NOT NULL DEFAULT 0;
        ALTER TABLE productos ADD COLUMN permite_stock_virtual INTEGER NOT NULL DEFAULT 0;
        ALTER TABLE productos ADD COLUMN descuenta_componentes_en_venta INTEGER NOT NULL DEFAULT 0;
        ALTER TABLE productos ADD COLUMN es_vendible INTEGER NOT NULL DEFAULT 1;
        ALTER TABLE productos ADD COLUMN es_inventariable INTEGER NOT NULL DEFAULT 1;
    """)

    # Backfill tipo_producto from legacy boolean columns (idempotent: only sets
    # rows that are still 'simple' so previous runs are not overwritten).
    conn.execute("""
        UPDATE productos
        SET    tipo_producto = 'compuesto'
        WHERE  es_compuesto   = 1
          AND  tipo_producto  = 'simple'
    """)
    conn.execute("""
        UPDATE productos
        SET    tipo_producto = 'procesable'
        WHERE  es_subproducto = 1
          AND  tipo_producto  = 'simple'
    """)

    # Backfill tipo_producto from active recipes when the product is still
    # classified as 'simple' — use tipo_receta on the recipe to infer the
    # canonical tipo_producto value.
    try:
        conn.execute("""
            UPDATE productos
            SET    tipo_producto = CASE pr.tipo_receta
                                       WHEN 'COMBINACION'  THEN 'compuesto'
                                       WHEN 'SUBPRODUCTO'  THEN 'procesable'
                                       WHEN 'PRODUCCION'   THEN 'producido'
                                       ELSE tipo_producto
                                   END
            FROM   product_recipes pr
            WHERE  pr.product_id  = productos.id
              AND  pr.is_active   = 1
              AND  productos.tipo_producto = 'simple'
        """)
    except Exception:
        # product_recipes may not exist in very old schemas — safe to skip
        pass

    # Backfill the new flag columns from the now-normalised tipo_producto.
    conn.execute("""
        UPDATE productos
        SET
            permite_receta                = CASE
                WHEN tipo_producto IN ('compuesto','procesable','producido') THEN 1
                ELSE 0
            END,
            permite_stock_virtual         = CASE
                WHEN tipo_producto = 'compuesto' THEN 1
                ELSE 0
            END,
            descuenta_componentes_en_venta = CASE
                WHEN tipo_producto = 'compuesto' THEN 1
                ELSE 0
            END,
            es_vendible                   = CASE
                WHEN tipo_producto = 'insumo' THEN 0
                ELSE 1
            END,
            es_inventariable              = CASE
                WHEN tipo_producto = 'servicio' THEN 0
                ELSE 1
            END
    """)
