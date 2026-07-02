"""104_rol_permisos_uuid_columns.py — NO-OP bajo Plan B born-clean UUIDv7.

Histórico: esta migración añadía columnas `uuid`/`rol_uuid`/`permiso_uuid` duales como preparación
incremental del corte UUID (pre-Plan B). Con el schema born-clean la identidad
canónica ya ES `id TEXT PRIMARY KEY` (UUIDv7): la columna dual está prohibida
(REGLA CERO — sin dualidad uuid/id) y no debe volver a crearse. Se conserva
registrada en el engine sólo para no alterar el ledger schema_migrations.
"""
from __future__ import annotations

import sqlite3


def run(conn: sqlite3.Connection) -> None:  # pragma: no cover - no-op documentado
    return None
