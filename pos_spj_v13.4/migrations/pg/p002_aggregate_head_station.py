"""p002 — La cabeza de cada agregado recuerda qué estación la escribió
(arquitectura híbrida, Slice 4).

`aggregate_version` es el ordinal LOCAL de la estación (Slice 2): dos estaciones
que tocan el mismo agregado llevan cuentas independientes. Para detectar una
regresión real (la misma estación reenvía una versión vieja) la ingesta compara
sólo contra la última versión escrita por ESA estación. Idempotente.
"""

from __future__ import annotations

DDL = (
    "ALTER TABLE sync_aggregate_heads"
    " ADD COLUMN IF NOT EXISTS last_station_id UUID REFERENCES sync_stations (id)",
)


def run(conn) -> None:
    with conn.cursor() as cur:
        for sentencia in DDL:
            cur.execute(sentencia)


up = run
