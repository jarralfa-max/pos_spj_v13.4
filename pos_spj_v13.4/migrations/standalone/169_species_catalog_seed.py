# migrations/standalone/169_species_catalog_seed.py
"""P0-A (§5.2) — semilla del catálogo canónico de especies (`species`).

El maestro exige `species_id` para tipos cárnicos (`MEAT_PRODUCT_TYPES`), pero la
tabla `species` (creada por el esquema de Productos, PROD-3) nacía vacía: el
formulario no tenía de dónde elegir y el alta de una canal cárnica fallaba con
`SpeciesRequiredError`. Esta migración siembra las especies comunes del giro
(cárnicos/aves/pesca) para que la UI seleccione por catálogo y guarde
`species.id` (UUID), nunca texto libre ni un UUID escrito a mano.

UUIDv7 vía `new_uuid()`; INSERT OR IGNORE por `code` UNIQUE (re-ejecutable).
No toca `products`.
"""

from __future__ import annotations

import logging

from backend.shared.ids import new_uuid

logger = logging.getLogger("spj.migrations.169")

# (code, name)
_SPECIES = (
    ("BOVINO", "Bovino (res)"),
    ("PORCINO", "Porcino (cerdo)"),
    ("AVE_POLLO", "Ave — pollo"),
    ("AVE_PAVO", "Ave — pavo"),
    ("AVE_PATO", "Ave — pato"),
    ("OVINO", "Ovino (borrego)"),
    ("CAPRINO", "Caprino (cabra)"),
    ("EQUINO", "Equino"),
    ("CONEJO", "Conejo"),
    ("PESCADO", "Pescado"),
    ("MARISCO", "Marisco"),
    ("OTRO", "Otra especie"),
)


def run(conn) -> None:
    if conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND "
                    "name='species'").fetchone() is None:
        logger.info("169: tabla species ausente; seed omitido.")
        return
    inserted = 0
    for code, name in _SPECIES:
        cur = conn.execute(
            "INSERT OR IGNORE INTO species (id, code, name, active) VALUES (?,?,?,1)",
            (new_uuid(), code, name))
        inserted += cur.rowcount or 0
    conn.commit()
    logger.info("169: especies sembradas (%d nuevas).", inserted)


up = run
