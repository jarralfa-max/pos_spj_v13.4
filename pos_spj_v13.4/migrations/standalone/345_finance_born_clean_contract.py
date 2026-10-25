"""345 — Contrato born-clean del esquema financiero (FIN-ERP, 2026-10-21;
corregido en la auditoría enterprise N05, 2026-10-25).

Regla del usuario (FIN-ERP): el esquema financiero nace limpio de
``finance_schema.py`` y **no se convierte ni se rescatan datos**.

Lo que hace, sin violar esa regla:

* Tabla del contrato que NO existe → se crea con el DDL canónico.
* Tabla que existe con columnas de un contrato anterior pero **VACÍA** → se
  vuelve a crear con el DDL canónico. No hay nada que rescatar, así que no es
  una conversión.
* Tabla con columnas anteriores **y con datos** → la migración se detiene SIN
  tocar nada y dice qué tablas son. Convertir datos financieros es una decisión
  explícita, no algo que una actualización haga sola.

Antes (N05) cualquier diferencia detenía el arranque con la instrucción de
«eliminar data/spj_pos_database.db»: la base COMPLETA, con ventas, clientes e
inventario. En la copia de la base real el motor se detenía aquí (39 tablas
financieras distintas, todas vacías): la siguiente actualización no habría
abierto la base real.
"""

from __future__ import annotations

import logging

from backend.domain.finance.exceptions import FinanceSchemaContractError
from backend.infrastructure.db.schema.finance_schema import (
    create_finance_schema,
    finance_schema_differences,
)

logger = logging.getLogger("spj.migrations.345")


def run(conn) -> None:
    diferencias = finance_schema_differences(conn)
    if not diferencias:
        logger.info("345: esquema financiero conforme al contrato born-clean.")
        return
    con_datos = {}
    vacias = []
    for tabla, columnas in sorted(diferencias.items()):
        if columnas == ["*"]:
            continue   # ausente: la crea el DDL canónico
        filas = conn.execute(f'SELECT COUNT(*) FROM "{tabla}"').fetchone()[0]
        if filas:
            con_datos[tabla] = filas
        else:
            vacias.append(tabla)
    if con_datos:
        detalle = ", ".join(f"{t} ({n} filas)" for t, n in sorted(con_datos.items())[:10])
        raise FinanceSchemaContractError(
            "El esquema financiero de esta base es anterior al contrato vigente y tiene "
            f"datos en {len(con_datos)} tabla(s): {detalle}. No se modificó nada. "
            "Convertir datos financieros requiere una decisión explícita; conserve esta "
            "base y su respaldo y solicite la conversión.")
    for tabla in vacias:
        conn.execute(f'DROP TABLE "{tabla}"')
    create_finance_schema(conn)
    pendientes = finance_schema_differences(conn)
    if pendientes:
        raise FinanceSchemaContractError(
            f"El esquema financiero no quedó conforme al contrato: {sorted(pendientes)[:8]}")
    conn.commit()
    logger.info("345: %s tablas financieras vacías recreadas y %s creadas con el contrato "
                "born-clean; ningún dato tocado.", len(vacias),
                sum(1 for c in diferencias.values() if c == ["*"]))


up = run
