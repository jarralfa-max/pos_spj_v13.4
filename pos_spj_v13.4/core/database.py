
# core/database.py — SHIM de compatibilidad v6.1
# Re-exporta todo desde core.db.connection (módulo canónico).
# Mantener este archivo para no romper imports en scripts/ y servicios legacy.
from core.db.connection import (
    get_connection, get_db, close_connection, transaction,
    execute_with_retry, set_db_path, DB_PATH, BASE_DIR,
    Connection, Database, _DatabaseShim,
)

# Alias adicionales usados por scripts
def get_db_connection():
    return get_connection()

__all__ = [
    "get_connection", "get_db", "get_db_connection", "close_connection",
    "transaction", "execute_with_retry", "set_db_path",
    "DB_PATH", "BASE_DIR", "Connection", "Database",
]

Database = Database

Database = Database

Connection = Connection

get_db = get_db

Connection = Connection

Connection = Connection

Connection = Connection

get_db = get_db

Connection = Connection

Database = Database

Connection = Connection

_open_raw = _open_raw

Connection = Connection

Database = Database
