"""Archive legacy inventory tables — NO-OP bajo Plan B born-clean.

Histórico: esta migración renombraba inventario_actual / branch_inventory /
movimientos_inventario a legacy_* para que el runtime nuevo no siguiera
usándolas como ruta operativa (FASE 7 pre-Plan B).

Plan B (born-clean UUIDv7, sin conservación de datos): una DB nueva nace ya con
el esquema canónico UUIDv7; no existe ruta legacy que archivar y una DB de
desarrollo contaminada se elimina y se recrea (docs/runbooks/dev_db_reset.md).
Renombrar tablas recién creadas y vacías a legacy_* sólo fabricaba tablas
muertas en cada instalación nueva (violación de REGLA 3), por lo que esta
migración queda como no-op documentado. NO se elimina del engine para no
alterar el ledger schema_migrations de instalaciones existentes.
"""
from __future__ import annotations

import sqlite3


def run(conn: sqlite3.Connection) -> None:  # pragma: no cover - no-op documentado
    return None
