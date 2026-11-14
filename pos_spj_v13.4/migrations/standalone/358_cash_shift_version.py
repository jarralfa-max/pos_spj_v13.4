"""358 — versión del turno para el compare-and-set de transiciones (SDLC-ARQ-SHIFT-004).

`cash_shifts` no tenía con qué detectar una escritura concurrente: suspender,
reanudar y preparar cierre hacían `UPDATE ... WHERE id=?` sobre lo que habían
leído antes. Cada transición compara ahora estado y versión y la incrementa.

La base nueva recibe la columna en el DDL de la 175; ésta la agrega a las
existentes. Los turnos que ya están abiertos arrancan en 1: no cambia su estado.
Idempotente.
"""

from __future__ import annotations


def run(conn) -> None:
    columnas = {fila[1] for fila in conn.execute("PRAGMA table_info(cash_shifts)")}
    if not columnas or "version" in columnas:
        return
    conn.execute(
        "ALTER TABLE cash_shifts ADD COLUMN version INTEGER NOT NULL DEFAULT 1"
        " CHECK(version>=1)")
    conn.commit()


up = run
