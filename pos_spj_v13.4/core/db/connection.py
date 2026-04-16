
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

def get_connection(path: Optional[str] = None) -> "DatabaseWrapper":
    """
    Devuelve la conexión thread-local envuelta en DatabaseWrapper.
    Crea una nueva si no existe o si está muerta.
    """

    db_path = path or _DB_PATH

    conn = getattr(_tls, "conn", None)

    if conn is not None:
        # Unwrap si ya es DatabaseWrapper para hacer el ping
        raw = conn._conn if isinstance(conn, DatabaseWrapper) else conn
        try:
            raw.execute("SELECT 1")
            # Asegurar que siempre retornamos DatabaseWrapper
            if isinstance(conn, DatabaseWrapper):
                return conn
            wrapped = DatabaseWrapper(conn)
            _tls.conn = wrapped
            return wrapped
        except Exception:
            logger.warning(
                "Conexión muerta en hilo %s — reconectando",
                threading.current_thread().name
            )
            try:
                raw.close()
            except Exception:
                pass
            _tls.conn = None

    raw_conn = _new_connection(db_path)
    wrapped = DatabaseWrapper(raw_conn)
    _tls.conn = wrapped
    return wrapped


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
# DATABASE WRAPPER — añade fetchall / fetchone / transaction
# a sqlite3.Connection para compatibilidad con repositorios.
# ─────────────────────────────────────────────────────────────

class DatabaseWrapper:
    """
    Envuelve sqlite3.Connection y expone la API extendida que usan
    los repositorios del ERP (fetchall, fetchone, transaction).

    Se usa automáticamente en get_connection() para que TODO el
    código que obtiene una conexión reciba esta interfaz unificada.
    """

    __slots__ = ("_conn",)

    def __init__(self, conn: sqlite3.Connection):
        object.__setattr__(self, "_conn", conn)

    # ── API extendida ─────────────────────────────────────────

    def fetchall(self, sql: str, params=()) -> list:
        """Ejecuta sql y retorna todas las filas."""
        return self._conn.execute(sql, params).fetchall()

    def fetchone(self, sql: str, params=()) -> Optional[sqlite3.Row]:
        """Ejecuta sql y retorna la primera fila o None."""
        return self._conn.execute(sql, params).fetchone()

    def transaction(self, name: str = ""):
        """Context manager de transacción con SAVEPOINT."""
        return transaction(self._conn)

    # ── Delegación total a sqlite3.Connection ────────────────

    def execute(self, sql: str, params=()):
        return self._conn.execute(sql, params)

    def executemany(self, sql: str, params):
        return self._conn.executemany(sql, params)

    def executescript(self, sql: str):
        return self._conn.executescript(sql)

    def commit(self):
        return self._conn.commit()

    def rollback(self):
        return self._conn.rollback()

    def close(self):
        return self._conn.close()

    def cursor(self):
        return self._conn.cursor()

    @property
    def row_factory(self):
        return self._conn.row_factory

    @row_factory.setter
    def row_factory(self, value):
        self._conn.row_factory = value

    @property
    def in_transaction(self):
        return self._conn.in_transaction

    def __getattr__(self, name: str):
        return getattr(self._conn, name)

    def __setattr__(self, name: str, value):
        if name == "_conn":
            object.__setattr__(self, name, value)
        else:
            setattr(self._conn, name, value)

    def __enter__(self):
        return self._conn.__enter__()

    def __exit__(self, *args):
        return self._conn.__exit__(*args)


def wrap(conn) -> "DatabaseWrapper":
    """Envuelve una conexión si todavía no es DatabaseWrapper."""
    if isinstance(conn, DatabaseWrapper):
        return conn
    return DatabaseWrapper(conn)


# ─────────────────────────────────────────────────────────────
# v13.4: VALIDACIÓN FAIL-FAST
# ─────────────────────────────────────────────────────────────

TABLAS_REQUERIDAS = [
    "usuarios", "productos", "clientes",
    "ventas", "configuraciones", "inventario",
]

# Reglas de equivalencia para esquemas donde hubo refactor de nombres.
_EQUIVALENCIAS_TABLAS = {
    "inventario": {"inventario", "inventario_actual"},
}


def verificar_tablas(conn) -> None:
    """Levanta RuntimeError si alguna tabla crítica falta en la DB.

    Se llama desde main.py justo después de ejecutar las migraciones
    para garantizar un arranque fail-fast antes de inicializar la UI.
    """
    cur = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'"
    )
    existentes = {r[0] for r in cur.fetchall()}

    faltantes = []
    for tabla in TABLAS_REQUERIDAS:
        opciones = _EQUIVALENCIAS_TABLAS.get(tabla, {tabla})
        if not (existentes & opciones):
            faltantes.append(tabla)
    if faltantes:
        raise RuntimeError(
            f"DB incompleta — tablas faltantes: {faltantes}"
        )


def _column_exists(conn: sqlite3.Connection, table_name: str, column_name: str) -> bool:
    try:
        rows = conn.execute(f"PRAGMA table_info({table_name})").fetchall()
    except Exception:
        return False
    for row in rows:
        # sqlite3.Row o tuple
        name = row["name"] if isinstance(row, sqlite3.Row) else row[1]
        if name == column_name:
            return True
    return False


def migrate_db(conn: sqlite3.Connection) -> None:
    """
    Migraciones defensivas de compatibilidad para DB legacy.
    - Agrega columnas faltantes `created_at` y `activo` donde se usan en queries.
    - Idempotente y seguro de ejecutar en cada arranque.
    """
    compat_columns = {
        "productos": [
            ("created_at", "TEXT DEFAULT (datetime('now'))"),
            ("activo", "INTEGER DEFAULT 1"),
        ],
        "clientes": [
            ("created_at", "TEXT DEFAULT (datetime('now'))"),
            ("activo", "INTEGER DEFAULT 1"),
        ],
        "proveedores": [
            ("created_at", "TEXT DEFAULT (datetime('now'))"),
            ("activo", "INTEGER DEFAULT 1"),
        ],
        "personal": [
            ("created_at", "TEXT DEFAULT (datetime('now'))"),
            ("activo", "INTEGER DEFAULT 1"),
        ],
        "recetas_produccion": [
            ("created_at", "TEXT DEFAULT (datetime('now'))"),
            ("activo", "INTEGER DEFAULT 1"),
        ],
    }
    for table_name, columns in compat_columns.items():
        table_exists = conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
            (table_name,),
        ).fetchone()
        if not table_exists:
            continue
        for column_name, ddl in columns:
            if _column_exists(conn, table_name, column_name):
                continue
            conn.execute(
                f"ALTER TABLE {table_name} ADD COLUMN {column_name} {ddl}"
            )
            logger.warning(
                "DB compat: columna agregada %s.%s",
                table_name,
                column_name,
            )
    conn.commit()


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
def get_db(path: str = None) -> "DatabaseWrapper":
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
    "DatabaseWrapper",
    "wrap",
    "Connection",
    "Database",
    "get_db",
    "migrate_db",
]
