
# core/db/connection.py — SPJ POS (stable edition)
"""
Gestión avanzada de conexiones SQLite para SPJ POS.

Características:
- Pool de conexiones thread-local (una conexión por hilo)
- WAL mode para alto rendimiento POS
- Retry automático ante "database is locked"
- Transacciones seguras con SAVEPOINT
- Compatibilidad backward con código legacy
"""

from __future__ import annotations
import sqlite3
import threading
import time
import logging
import os
from contextlib import contextmanager
from typing import Optional

logger = logging.getLogger("spj.db")

# ─────────────────────────────────────────────────────────────
# CONFIGURACIÓN
# ─────────────────────────────────────────────────────────────

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../"))

_DB_PATH = os.path.join(BASE_DIR, "data", "spj.db")
_TIMEOUT = 5.0
_MAX_RETRY = 5

_tls = threading.local()  # thread-local storage


# ─────────────────────────────────────────────────────────────
# PATH DB
# ─────────────────────────────────────────────────────────────

def set_db_path(path: str) -> None:
    global _DB_PATH
    _DB_PATH = path


def get_db_path() -> str:
    return _DB_PATH


# ─────────────────────────────────────────────────────────────
# CREACIÓN DE CONEXIÓN
# ─────────────────────────────────────────────────────────────

def _new_connection(path: str) -> sqlite3.Connection:
    """Crea una nueva conexión SQLite optimizada para POS."""

    db_dir = os.path.dirname(path)
    if db_dir:  # Solo creamos la carpeta si la ruta realmente tiene una
        os.makedirs(db_dir, exist_ok=True)

    conn = sqlite3.connect(
        path,
        timeout=_TIMEOUT,
        isolation_level=None,
        check_same_thread=False
    )

    conn.row_factory = sqlite3.Row

    conn.executescript(
        """
        PRAGMA journal_mode=WAL;
        PRAGMA synchronous=NORMAL;
        PRAGMA foreign_keys=ON;
        PRAGMA busy_timeout=5000;
        PRAGMA cache_size=-32768;
        PRAGMA temp_store=MEMORY;
        PRAGMA mmap_size=268435456;
        """
    )

    logger.debug(
        "Nueva conexión DB para hilo %s",
        threading.current_thread().name
    )

    return conn


# ─────────────────────────────────────────────────────────────
# OBTENER CONEXIÓN
# ─────────────────────────────────────────────────────────────

def get_connection(path: Optional[str] = None) -> sqlite3.Connection:
    """
    Devuelve la conexión thread-local.
    Crea una nueva si no existe.
    """

    db_path = path or _DB_PATH

    conn = getattr(_tls, "conn", None)

    if conn is not None:
        try:
            conn.execute("SELECT 1")
            return conn
        except Exception:
            logger.warning(
                "Conexión muerta en hilo %s — reconectando",
                threading.current_thread().name
            )
            try:
                conn.close()
            except Exception:
                pass

            _tls.conn = None

    conn = _new_connection(db_path)
    _tls.conn = conn

    return conn


# ─────────────────────────────────────────────────────────────
# CIERRE DE CONEXIONES
# ─────────────────────────────────────────────────────────────

def close_thread_connection() -> None:
    """Cierra la conexión del hilo actual."""
    conn = getattr(_tls, "conn", None)

    if conn:
        try:
            conn.close()
        except Exception:
            pass

        _tls.conn = None


def close_connection(conn: sqlite3.Connection) -> None:
    """Cierra una conexión SQLite de forma segura."""
    try:
        if conn:
            conn.close()
    except Exception:
        pass


# ─────────────────────────────────────────────────────────────
# EJECUCIÓN CON RETRY
# ─────────────────────────────────────────────────────────────

def execute_with_retry(
    conn: sqlite3.Connection,
    sql: str,
    params: tuple = (),
    retries: int = _MAX_RETRY
):

    delay = 0.05

    for attempt in range(retries):
        try:
            return conn.execute(sql, params)

        except sqlite3.OperationalError as e:

            if "locked" in str(e).lower() and attempt < retries - 1:

                logger.warning(
                    "DB locked (intento %d/%d) — esperando %.2fs",
                    attempt + 1,
                    retries,
                    delay
                )

                time.sleep(delay)
                delay = min(delay * 2, 2.0)

            else:
                raise


# ─────────────────────────────────────────────────────────────
# TRANSACCIONES
# ─────────────────────────────────────────────────────────────

@contextmanager
def transaction(conn: sqlite3.Connection):
    """
    Context manager para transacciones seguras.
    Permite transacciones anidadas usando SAVEPOINT.
    """

    import uuid

    sp = f"sp_{uuid.uuid4().hex[:8]}"

    conn.execute(f"SAVEPOINT {sp}")

    try:
        yield conn
        conn.execute(f"RELEASE SAVEPOINT {sp}")

    except Exception:
        try:
            conn.execute(f"ROLLBACK TO SAVEPOINT {sp}")
        except Exception:
            pass

        raise


# ─────────────────────────────────────────────────────────────
# SHIMS DE COMPATIBILIDAD
# ─────────────────────────────────────────────────────────────

class _DatabaseShim:
    """
    Shim para código legacy que usaba:
    database.Connection
    """

    def __init__(self, path: str = None):
        self._conn = get_connection(path)

    def __getattr__(self, name):
        return getattr(self._conn, name)

    def __enter__(self):
        return self._conn

    def __exit__(self, *args):
        pass


Connection = _DatabaseShim


class Database:
    """
    Clase de compatibilidad para código antiguo que usaba Database().
    """

    def __init__(self, path: str = None):
        self.conn = get_connection(path)

    def get_connection(self):
        return self.conn

    def execute(self, *args, **kwargs):
        return self.conn.execute(*args, **kwargs)

    def commit(self):
        self.conn.commit()

    def rollback(self):
        self.conn.rollback()

    def close(self):
        close_connection(self.conn)


# Alias legacy
def get_db(path: str = None) -> sqlite3.Connection:
    return get_connection(path)


# Export público
DB_PATH = _DB_PATH


__all__ = [
    "BASE_DIR",
    "DB_PATH",
    "get_connection",
    "close_connection",
    "close_thread_connection",
    "execute_with_retry",
    "transaction",
    "Connection",
    "Database",
    "get_db",
]