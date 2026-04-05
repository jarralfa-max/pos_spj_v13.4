
# database/conexion.py — SHIM de compatibilidad v6.1
# Re-exporta todo desde core.db.connection (módulo canónico).
# main.py y pos_adapter.py importan desde aquí — no romper.
from __future__ import annotations
from core.db.connection import (
    get_connection, get_db, close_connection, transaction,
    execute_with_retry, set_db_path, DB_PATH, BASE_DIR,
    Connection, Database,
)
import logging, sqlite3

logger = logging.getLogger("spj.db.conexion")

# Alias usados directamente por main.py y pos_adapter.py
def get_db_connection() -> sqlite3.Connection:
    return get_connection()

def aplicar_migraciones_estructurales(conn=None):
    """Legacy no-op — las migraciones corren via migrations/engine.py en main.py."""
    pass

# ── bcrypt helpers (delegados a security/auth.py) ─────────────────────────────
def verificar_password(usuario: str, password: str) -> bool:
    from security.auth import autenticar
    try:
        autenticar(usuario, password)
        return True
    except Exception:
        return False

def migrar_password_a_bcrypt(usuario_id: int, password_plano: str) -> None:
    try:
        import bcrypt
        hashed = (lambda p: __import__("hashlib").sha256(p.encode()).hexdigest())(password_plano)
        conn = get_connection()
        conn.execute(
            "UPDATE usuarios SET contrasena=? WHERE id=?",
            (hashed, usuario_id)
        )
        conn.commit()
    except Exception as e:
        logger.warning("migrar_password_a_bcrypt: %s", e)

__all__ = [
    "get_connection", "get_db", "get_db_connection", "close_connection",
    "transaction", "execute_with_retry", "set_db_path", "DB_PATH",
    "verificar_password", "migrar_password_a_bcrypt",
    "aplicar_migraciones_estructurales",
]
