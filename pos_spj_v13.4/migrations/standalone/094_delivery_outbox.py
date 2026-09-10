"""Migración 094 — INERTE, igual que la 093.

Su cuerpo entero era `DeliverySchemaMigrator(conn).ensure_schema()`, es decir
exactamente la misma llamada idempotente que ya hacía la 093: no añadía nada
propio. Al desaparecer `core/`, esa clase ya no existe y no se recupera del
historial (§18).

El razonamiento completo y las mediciones están en
`093_delivery_schema_migrator.py`. El archivo se conserva para que su número
siga presente en la cadena de versiones de esquema.
"""
from __future__ import annotations

import sqlite3


def run(conn: sqlite3.Connection) -> None:
    """No hace nada, a propósito. Ver `093_delivery_schema_migrator.py`."""


up = run
