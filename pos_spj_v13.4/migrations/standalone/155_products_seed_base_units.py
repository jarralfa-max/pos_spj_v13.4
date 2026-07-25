# migrations/standalone/155_products_seed_base_units.py
"""P0-03 — semilla del catálogo canónico de unidades de medida (`units_of_measure`).

El maestro `products.base_unit_id` debe referenciar el UUID de una unidad real, no
el texto libre ("KG"/"PZA"). Antes de este seed el catálogo estaba vacío, por lo que
el formulario guardaba el código como si fuera id. Esta migración siembra las
unidades base (idempotente por `code` UNIQUE) para que la UI seleccione por catálogo
y guarde `units_of_measure.id`.

UUIDv7 vía `new_uuid()`; INSERT OR IGNORE (re-ejecutable). No toca `products`.
"""

from __future__ import annotations

import logging

from backend.shared.ids import new_uuid

logger = logging.getLogger("spj.migrations.155")

# (code, name, dimension)
_UNITS = (
    ("KG", "Kilogramo", "WEIGHT"),
    ("G", "Gramo", "WEIGHT"),
    ("LB", "Libra", "WEIGHT"),
    ("TON", "Tonelada", "WEIGHT"),
    ("PZA", "Pieza", "COUNT"),
    ("DOC", "Docena", "COUNT"),
    ("PAR", "Par", "COUNT"),
    ("LT", "Litro", "VOLUME"),
    ("ML", "Mililitro", "VOLUME"),
    ("GAL", "Galón", "VOLUME"),
    ("M", "Metro", "LENGTH"),
    ("CM", "Centímetro", "LENGTH"),
    ("CAJA", "Caja", "PACKAGE"),
    ("PAQ", "Paquete", "PACKAGE"),
    ("BOLSA", "Bolsa", "PACKAGE"),
    ("BULTO", "Bulto", "PACKAGE"),
    ("SERV", "Servicio", "OTHER"),
)


def run(conn) -> None:
    if conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND "
                    "name='units_of_measure'").fetchone() is None:
        logger.info("155: units_of_measure ausente; seed omitido.")
        return
    inserted = 0
    for code, name, dimension in _UNITS:
        cur = conn.execute(
            "INSERT OR IGNORE INTO units_of_measure (id, code, name, dimension, active) "
            "VALUES (?,?,?,?,1)", (new_uuid(), code, name, dimension))
        inserted += cur.rowcount or 0
    conn.commit()
    logger.info("155: unidades base sembradas (%d nuevas).", inserted)


up = run
