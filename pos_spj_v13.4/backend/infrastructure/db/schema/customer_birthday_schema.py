"""Cumpleaños del cliente (2026-10-03, migración 297).

Decisión del usuario: fecha de nacimiento OPCIONAL y con consentimiento.
Tabla propia del contexto de Clientes (no columna del maestro): es un dato
personal que sólo existe si el cliente lo autorizó, y se borra entero si lo
retira. Día y mes bastan para el beneficio; el año es opcional.
"""

from __future__ import annotations

_DDL = (
    """
    CREATE TABLE IF NOT EXISTS customer_birthdays (
        customer_id TEXT NOT NULL PRIMARY KEY,
        birth_month INTEGER NOT NULL,
        birth_day INTEGER NOT NULL,
        birth_year INTEGER,
        consent_at TEXT NOT NULL,
        recorded_by_user_id TEXT,
        updated_at TEXT NOT NULL
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_customer_birthdays_month_day"
    " ON customer_birthdays (birth_month, birth_day)",
)


def create_customer_birthday_schema(connection) -> None:
    for ddl in _DDL:
        connection.execute(ddl)


__all__ = ["create_customer_birthday_schema"]
