"""
Migration 066: Unificación de esquemas de recetas
=================================================
Contexto:
  - Esquema legacy: recetas + receta_componentes (usado por ProductionEngine.close_batch)
  - Esquema nuevo:  product_recipes + product_recipe_components (usado por RecipeEngine)

Ambos esquemas coexisten. Sin esta migración, una receta registrada en uno
no es visible en el otro, lo que causa "RECETA_SIN_COMPONENTES" en RecipeEngine
o que ProductionEngine no encuentre rendimiento_esperado_pct.

Esta migración:
  1. Agrega columnas de compatibilidad a product_recipes (tipo_receta, unidad_base,
     rendimiento_esperado_pct, merma_esperada_pct, legacy_receta_id)
  2. Agrega columna legacy_receta_id a product_recipe_components
  3. Crea vista recetas_unificada — consulta única para ambos esquemas
  4. Copia recetas existentes del esquema legacy → product_recipes (sin duplicar)
"""


def run(conn):
    # ── 1. Columnas de puente en product_recipes ────────────────────────────
    _col(conn, "product_recipes", "tipo_receta TEXT DEFAULT 'subproducto'")
    _col(conn, "product_recipes", "unidad_base TEXT DEFAULT 'kg'")
    _col(conn, "product_recipes", "rendimiento_esperado_pct REAL DEFAULT 0")
    _col(conn, "product_recipes", "merma_esperada_pct REAL DEFAULT 0")
    _col(conn, "product_recipes", "peso_promedio_kg REAL DEFAULT 1.0")
    _col(conn, "product_recipes", "legacy_receta_id INTEGER")
    _col(conn, "product_recipes", "output_product_id INTEGER")

    # ── 2. Columna de puente en product_recipe_components ──────────────────
    _col(conn, "product_recipe_components", "legacy_receta_componente_id INTEGER")
    _col(conn, "product_recipe_components", "cantidad REAL DEFAULT 0")
    _col(conn, "product_recipe_components", "rendimiento_porcentaje REAL DEFAULT 0")
    _col(conn, "product_recipe_components", "merma_porcentaje REAL DEFAULT 0")
    _col(conn, "product_recipe_components", "unidad TEXT DEFAULT 'kg'")

    # ── 3. Vista unificada (para consultas agnósticas al esquema) ──────────
    conn.execute("DROP VIEW IF EXISTS recetas_unificada")
    conn.execute("""
        CREATE VIEW recetas_unificada AS
        -- Esquema nuevo (product_recipes) — fuente canónica
        SELECT
            pr.id                                         AS id,
            COALESCE(pr.nombre_receta, p.nombre, '')      AS nombre,
            COALESCE(pr.tipo_receta, 'subproducto')       AS tipo_receta,
            COALESCE(pr.output_product_id,
                     pr.base_product_id,
                     pr.product_id)                       AS producto_base_id,
            COALESCE(pr.peso_promedio_kg, 1.0)            AS peso_promedio_kg,
            COALESCE(pr.unidad_base, 'kg')                AS unidad_base,
            pr.is_active                                  AS activo,
            pr.rendimiento_esperado_pct,
            pr.merma_esperada_pct,
            pr.legacy_receta_id,
            'product_recipes'                             AS origen
        FROM product_recipes pr
        LEFT JOIN productos p ON p.id = COALESCE(pr.output_product_id,
                                                  pr.base_product_id,
                                                  pr.product_id)
        WHERE pr.is_active = 1

        UNION ALL

        -- Esquema legacy (recetas) — solo los que NO tienen equivalente nuevo
        SELECT
            r.id                     AS id,
            r.nombre                 AS nombre,
            r.tipo_receta            AS tipo_receta,
            r.producto_base_id       AS producto_base_id,
            r.peso_promedio_kg       AS peso_promedio_kg,
            r.unidad_base            AS unidad_base,
            r.activo                 AS activo,
            r.rendimiento_esperado_pct,
            r.merma_esperada_pct,
            NULL                     AS legacy_receta_id,
            'recetas'                AS origen
        FROM recetas r
        WHERE r.activo = 1
          AND NOT EXISTS (
              SELECT 1 FROM product_recipes pr
              WHERE pr.legacy_receta_id = r.id
          )
    """)

    # ── 4. Migrar recetas legacy → product_recipes (sin duplicar) ─────────
    legacy_rows = conn.execute(
        "SELECT * FROM recetas WHERE activo=1"
    ).fetchall()

    migrated = 0
    for r in legacy_rows:
        already = conn.execute(
            "SELECT id FROM product_recipes WHERE legacy_receta_id=?",
            (r["id"],)
        ).fetchone()
        if already:
            continue

        # Usar producto_base_id como product_id y output_product_id
        cur = conn.execute("""
            INSERT INTO product_recipes (
                product_id, piece_product_id, base_product_id,
                output_product_id, nombre_receta, tipo_receta,
                unidad_base, peso_promedio_kg,
                rendimiento_esperado_pct, merma_esperada_pct,
                total_rendimiento, total_merma,
                is_active, activa, legacy_receta_id, created_at
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,1,1,?,datetime('now'))
        """, (
            r["producto_base_id"],
            r["producto_base_id"],
            r["producto_base_id"],
            r["producto_base_id"],
            r["nombre"],
            r["tipo_receta"],
            r["unidad_base"] or "kg",
            r["peso_promedio_kg"] or 1.0,
            r["rendimiento_esperado_pct"] or 0,
            r["merma_esperada_pct"] or 0,
            r["rendimiento_esperado_pct"] or 0,
            r["merma_esperada_pct"] or 0,
            r["id"],
        ))
        new_recipe_id = cur.lastrowid

        # Migrar componentes legacy → product_recipe_components
        comps = conn.execute(
            "SELECT * FROM receta_componentes WHERE receta_id=?",
            (r["id"],)
        ).fetchall()
        for c in comps:
            already_c = conn.execute(
                "SELECT id FROM product_recipe_components "
                "WHERE recipe_id=? AND component_product_id=?",
                (new_recipe_id, c["producto_id"])
            ).fetchone()
            if already_c:
                continue
            conn.execute("""
                INSERT INTO product_recipe_components (
                    recipe_id, component_product_id,
                    rendimiento_pct, merma_pct,
                    rendimiento_porcentaje, merma_porcentaje,
                    cantidad, unidad, orden,
                    legacy_receta_componente_id
                ) VALUES (?,?,?,?,?,?,?,?,?,?)
            """, (
                new_recipe_id,
                c["producto_id"],
                c["rendimiento_porcentaje"] or 0,
                c["merma_porcentaje"] or 0,
                c["rendimiento_porcentaje"] or 0,
                c["merma_porcentaje"] or 0,
                c["cantidad"] or 0,
                c["unidad"] or "kg",
                0,
                c["id"],
            ))
        migrated += 1

    try:
        conn.commit()
    except Exception:
        pass

    import logging
    logging.getLogger(__name__).info(
        "Migration 066: %d recetas legacy migradas a product_recipes; "
        "vista recetas_unificada creada.", migrated
    )


def _col(conn, table, col_def):
    try:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {col_def}")
    except Exception:
        pass  # columna ya existe — ignorar
