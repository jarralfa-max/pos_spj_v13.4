"""265 — repara las recetas que la migración 152 copió con tipos inválidos.

QUÉ PASABA, MEDIDO (2026-09-18)
--------------------------------
La 152 copió los dos catálogos legacy de recetas al canónico, pero con valores
que el dominio no reconoce, así que **toda receta migrada era ilegible** para
`RecipeRepository` — al hidratarla se levanta `ValueError`:

* `recipe_outputs.output_type = 'MAIN'`: el enum `OutputType` sólo tiene
  `MAIN_PRODUCT`.
* `recipes.recipe_type`: la 152 copiaba el `tipo_receta` legacy en mayúsculas
  (`PRODUCCION`, `COMBINACION`, `SUBPRODUCTO`) o ponía `PROCESSING` por omisión.
  Ninguno existe en `RecipeType`.

Se destapó al llevar la explosión de compras al catálogo canónico (Fase 2): la
prueba que pasa lo heredado por la 152 reventaba al leer la receta.

LA TRADUCCIÓN — sólo la que el legacy deja escrita
---------------------------------------------------
La migración 085 dice qué significaba cada tipo, porque de él deducía el tipo de
producto:

    PRODUCCION  -> el producto es "producido"   -> PRODUCTION_BOM
    COMBINACION -> el producto es "compuesto"   -> SALES_EXPLOSION
    PROCESSING  -> (el valor por omisión que inventó la 152) -> PROCESSING_RECIPE

**SUBPRODUCTO NO SE ADIVINA.** Según la 085 el producto dueño de esa receta es
"procesable": el que se DESPIEZA. La 152 lo copió como "consumir componentes
para fabricarlo", que es lo contrario. Traducirlo a cualquier tipo lo pondría a
consumir inventario al comprar o al vender según una lectura que nadie
verificó. Queda como `PROCESSING_RECIPE` para que se pueda leer y abrir en
Productos, pero sus versiones ACTIVAS pasan a `UNDER_REVIEW`: no explotan en
ninguna parte hasta que alguien la revise y la vuelva a aprobar por el flujo
normal. Mismo trato para cualquier otro valor desconocido.

En la base real no hay recetas (medido en sólo lectura), así que hoy esto no
cambia ningún dato. Existe para las instalaciones que sí las tengan.

IDEMPOTENTE: sólo toca valores que no pertenecen a los enums.
"""

from __future__ import annotations

import logging

logger = logging.getLogger("spj.migrations.265")

VALID_RECIPE_TYPES = frozenset({
    "SALES_EXPLOSION", "PRODUCTION_BOM", "PROCESSING_RECIPE", "PACKAGING_BOM",
    "DISASSEMBLY", "CUTTING_YIELD", "FORMULA", "MARINATION", "GRINDING", "MIXING",
})
VALID_OUTPUT_TYPES = frozenset({"MAIN_PRODUCT", "CO_PRODUCT", "BY_PRODUCT", "WASTE", "LOSS"})

#: Lo que el legacy deja escrito (migración 085). Todo lo demás va a revisión.
LEGACY_RECIPE_TYPES = {
    "PRODUCCION": "PRODUCTION_BOM",
    "COMBINACION": "SALES_EXPLOSION",
    "PROCESSING": "PROCESSING_RECIPE",
}
UNKNOWN_FALLBACK = "PROCESSING_RECIPE"

LEGACY_OUTPUT_TYPES = {"MAIN": "MAIN_PRODUCT"}


def _table_exists(conn, name: str) -> bool:
    return conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,)
    ).fetchone() is not None


def run(conn) -> None:
    if not (_table_exists(conn, "recipes") and _table_exists(conn, "recipe_versions")):
        logger.info("265: el catálogo canónico de recetas no existe; nada que reparar.")
        return

    salidas = 0
    if _table_exists(conn, "recipe_outputs"):
        for viejo, nuevo in LEGACY_OUTPUT_TYPES.items():
            salidas += conn.execute(
                "UPDATE recipe_outputs SET output_type=? WHERE output_type=?",
                (nuevo, viejo)).rowcount or 0

    traducidas = en_revision = 0
    marcadores = ",".join("?" * len(VALID_RECIPE_TYPES))
    invalidas = conn.execute(
        f"SELECT id, recipe_type FROM recipes WHERE recipe_type NOT IN ({marcadores})",
        tuple(sorted(VALID_RECIPE_TYPES))).fetchall()
    for fila in invalidas:
        receta_id, tipo = fila[0], str(fila[1] or "").strip().upper()
        if tipo in LEGACY_RECIPE_TYPES:
            conn.execute("UPDATE recipes SET recipe_type=? WHERE id=?",
                         (LEGACY_RECIPE_TYPES[tipo], receta_id))
            traducidas += 1
            continue
        conn.execute("UPDATE recipes SET recipe_type=? WHERE id=?",
                     (UNKNOWN_FALLBACK, receta_id))
        conn.execute("UPDATE recipe_versions SET status='UNDER_REVIEW'"
                     " WHERE recipe_id=? AND status='ACTIVE'", (receta_id,))
        en_revision += 1
        logger.warning("265: receta %s de tipo legacy %r sin traducción conocida; "
                       "queda EN REVISIÓN hasta que alguien la clasifique.", receta_id, tipo)

    conn.commit()
    logger.info("265: %s salidas, %s recetas traducidas, %s en revisión.",
                salidas, traducidas, en_revision)


up = run
