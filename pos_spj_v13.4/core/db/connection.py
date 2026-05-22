
# core/db/connection.py — SPJ POS (stable edition)
"""
Gestión avanzada de conexiones SQLite para SPJ POS.

Características:
- Pool de conexiones thread-local (una conexión por hilo)
- WAL mode para alto rendimiento POS
- Retry automático ante "database is locked"
- Transacciones seguras con SAVEPOINT
- Compatibilidad backward con código legacy

Ruta canónica de BD:
    <paquete ERP>/data/spj_pos_database.db

IMPORTANTE:
El default de este módulo debe coincidir con `main.py`. Así evitamos que
servicios que llamen `get_connection()` antes del bootstrap creen otra BD
como `data/spj.db` o `spj_pos_database.db` fuera de `/data`.
"""

from __future__ import annotations
import sqlite3
import threading
import time
import logging
import os
from contextlib import contextmanager
from typing import Optional

logger = logging.getLogger("spj.connection")

# ─────────────────────────────────────────────────────────────
# CONFIGURACIÓN
# ─────────────────────────────────────────────────────────────

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../"))
DATA_DIR = os.path.join(BASE_DIR, "data")
CANONICAL_DB_FILENAME = "spj_pos_database.db"
CANONICAL_DB_PATH = os.path.join(DATA_DIR, CANONICAL_DB_FILENAME)

_DB_PATH = CANONICAL_DB_PATH
DB_PATH = CANONICAL_DB_PATH  # alias legacy importado por core/database.py
_TIMEOUT = 5.0
_MAX_RETRY = 5

_tls = threading.local()  # thread-local storage


# ─────────────────────────────────────────────────────────────
# PATH DB
# ─────────────────────────────────────────────────────────────

def set_db_path(path: str) -> None:
    """Registra la ruta de BD para el pool de conexiones.

    Se recomienda pasar siempre la ruta canónica:
    `<paquete ERP>/data/spj_pos_database.db`.
    """
    global _DB_PATH, DB_PATH
    _DB_PATH = path
    DB_PATH = path


def get_db_path() -> str:
    return _DB_PATH


def get_canonical_db_path() -> str:
    """Devuelve la ruta única esperada para la BD del ERP."""
    return CANONICAL_DB_PATH


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
        check_same_thread=False,
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
        "Nueva conexión DB para hilo %s: %s",
        threading.current_thread().name,
        path,
    )

    return conn


def _open_raw(path: Optional[str] = None) -> sqlite3.Connection:
    """Alias legacy: abre conexión SQLite cruda."""
    return _new_connection(path or _DB_PATH)


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
                threading.current_thread().name,
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


def get_db(path: Optional[str] = None) -> "DatabaseWrapper":
    """Alias legacy de get_connection()."""
    return get_connection(path)


# ─────────────────────────────────────────────────────────────
# COMPATIBILIDAD LEGACY
# ─────────────────────────────────────────────────────────────

def wrap(conn) -> "DatabaseWrapper":
    """Envuelve una conexión SQLite en DatabaseWrapper.

    Muchos servicios legacy importan `wrap` desde `core.db.connection`.
    Este helper se mantiene para compatibilidad y evita romper imports.
    """
    if isinstance(conn, DatabaseWrapper):
        return conn
    if hasattr(conn, "_conn") and isinstance(getattr(conn, "_conn"), sqlite3.Connection):
        return conn
    if isinstance(conn, sqlite3.Connection):
        return DatabaseWrapper(conn)
    return DatabaseWrapper(conn)


def unwrap(conn):
    """Devuelve la conexión SQLite cruda cuando el objeto está envuelto."""
    return conn._conn if isinstance(conn, DatabaseWrapper) else conn


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


def close_connection(conn=None) -> None:
    """Cierra una conexión SQLite de forma segura."""
    try:
        if conn is None:
            close_thread_connection()
            return
        if conn:
            unwrap(conn).close()
    except Exception:
        pass


# ─────────────────────────────────────────────────────────────
# EJECUCIÓN CON RETRY
# ─────────────────────────────────────────────────────────────

def execute_with_retry(
    conn,
    sql: str,
    params: tuple = (),
    retries: int = _MAX_RETRY,
):
    raw_conn = unwrap(conn)
    delay = 0.05

    for attempt in range(retries):
        try:
            return raw_conn.execute(sql, params)

        except sqlite3.OperationalError as e:
            if "locked" in str(e).lower() and attempt < retries - 1:
                logger.warning(
                    "DB locked (intento %d/%d) — esperando %.2fs",
                    attempt + 1,
                    retries,
                    delay,
                )
                time.sleep(delay)
                delay = min(delay * 2, 2.0)
            else:
                raise


# ─────────────────────────────────────────────────────────────
# TRANSACCIONES
# ─────────────────────────────────────────────────────────────

# Per-connection reentrant lock — serializes SAVEPOINT operations when a single
# sqlite3.Connection is shared across multiple threads (test scenarios and
# write-heavy workloads where WAL alone is insufficient).
_conn_locks: dict = {}
_conn_locks_guard = threading.Lock()


def _get_conn_lock(conn: sqlite3.Connection) -> threading.RLock:
    key = id(conn)
    with _conn_locks_guard:
        lock = _conn_locks.get(key)
        if lock is None:
            lock = threading.RLock()
            _conn_locks[key] = lock
        return lock


@contextmanager
def transaction(conn):
    """
    Context manager para transacciones seguras.
    Permite transacciones anidadas usando SAVEPOINT.
    Adquiere un RLock por conexión para serializar acceso multi-hilo.
    """

    import uuid

    raw_conn = unwrap(conn)
    sp = f"sp_{uuid.uuid4().hex[:8]}"
    lock = _get_conn_lock(raw_conn)

    with lock:
        raw_conn.execute(f"SAVEPOINT {sp}")

        try:
            yield raw_conn
            raw_conn.execute(f"RELEASE SAVEPOINT {sp}")

        except Exception:
            try:
                raw_conn.execute(f"ROLLBACK TO SAVEPOINT {sp}")
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

    def __init__(self, conn):
        object.__setattr__(self, "_conn", conn)

    # ── Delegación básica ─────────────────────────────────────────────────────
    def __getattr__(self, name):
        return getattr(self._conn, name)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    # ── Helpers usados por repositorios ───────────────────────────────────────
    def fetchall(self, sql: str, params: tuple = ()):  # noqa: D401
        """Ejecuta SQL y devuelve todas las filas."""
        return self._conn.execute(sql, params).fetchall()

    def fetchone(self, sql: str, params: tuple = ()):  # noqa: D401
        """Ejecuta SQL y devuelve una fila."""
        return self._conn.execute(sql, params).fetchone()

    @contextmanager
    def transaction(self):
        with transaction(self._conn) as conn:
            yield conn

    # ── Métodos críticos explícitos para sqlite3-like API ─────────────────────
    def execute(self, *args, **kwargs):
        return self._conn.execute(*args, **kwargs)

    def executemany(self, *args, **kwargs):
        return self._conn.executemany(*args, **kwargs)

    def executescript(self, *args, **kwargs):
        return self._conn.executescript(*args, **kwargs)

    def commit(self):
        return self._conn.commit()

    def rollback(self):
        return self._conn.rollback()

    def close(self):
        return self._conn.close()


# Aliases legacy usados por core/database.py y otros módulos antiguos.
_DatabaseShim = DatabaseWrapper
Connection = DatabaseWrapper
Database = DatabaseWrapper


# ─────────────────────────────────────────────────────────────
# MIGRACIÓN / VALIDACIÓN LEGACY
# ─────────────────────────────────────────────────────────────

def migrate_db(conn) -> None:
    """Compatibilidad legacy.

    La migración formal vive en `migrations.engine.up`. Esta función existe para
    los fallbacks antiguos de `main.py` y scripts.
    """
    try:
        from migrations import engine as migrator
        migrator.up(unwrap(conn))
    except Exception as exc:
        logger.warning("migrate_db fallback no pudo ejecutar migrations.engine: %s", exc)


def verificar_tablas(conn) -> bool:
    """Verificación mínima de BD para compatibilidad legacy."""
    try:
        raw = unwrap(conn)
        raw.execute("SELECT name FROM sqlite_master WHERE type='table' LIMIT 1").fetchone()
        return True
    except Exception as exc:
        logger.warning("verificar_tablas falló: %s", exc)
        return False


__all__ = [
    "BASE_DIR", "DB_PATH", "CANONICAL_DB_PATH", "get_canonical_db_path",
    "set_db_path", "get_db_path", "get_connection", "get_db",
    "close_connection", "close_thread_connection", "execute_with_retry",
    "transaction", "wrap", "unwrap", "migrate_db", "verificar_tablas",
    "DatabaseWrapper", "_DatabaseShim", "Connection", "Database", "_open_raw",
]
