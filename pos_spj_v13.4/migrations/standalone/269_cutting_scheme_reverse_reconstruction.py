"""269 — la marca de reconstrucción inversa pasa al ESQUEMA DE CORTE.

POR QUÉ (Fase 7, 2026-09-19)
----------------------------
La reconstrucción inversa (vender el producto entero armándolo con sus partes
cuando no hay existencia directa) leía sólo recetas de tipo Desensamble. Pero el
despiece que Productos captura y que Cárnico EJECUTA es el esquema de corte
(`cutting_schemes`): el mismo despiece había que definirlo dos veces, y el que
de verdad se usa no se podía revertir. Decisión del usuario: el esquema de corte
es la fuente única.

Vuelve a correr `create_products_schema` (misma convención que 137/253/258), que
declara `cutting_schemes.reverse_reconstruction_allowed` y la agrega con ALTER a
tablas creadas antes. Por omisión 0: ningún despiece queda reversible por la
migración; se habilita esquema por esquema desde Productos → Despiece.

`recipes.reverse_reconstruction_allowed` (258) queda inactiva; no se borra.
"""

from __future__ import annotations

import logging

from backend.infrastructure.db.schema.products_schema import create_products_schema

logger = logging.getLogger("spj.migrations.269")


def run(conn) -> None:
    create_products_schema(conn)
    conn.commit()
    logger.info("269: cutting_schemes.reverse_reconstruction_allowed asegurada.")


up = run
