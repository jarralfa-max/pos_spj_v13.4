
# core/db/integrity.py — SPJ POS v10
"""Verifica integridad de la BD en cada arranque."""
from __future__ import annotations
import logging
logger = logging.getLogger("spj.db.integrity")

def check_integrity(conn) -> tuple[bool, list[str]]:
    """
    Ejecuta PRAGMA integrity_check y quick_check.
    Retorna (ok: bool, mensajes: list[str])
    """
    errors = []
    try:
        rows = conn.execute("PRAGMA integrity_check").fetchall()
        msgs = [r[0] for r in rows]
        if msgs != ["ok"]:
            errors.extend(msgs)
            logger.error("integrity_check FAILED: %s", msgs)
        else:
            logger.debug("integrity_check: OK")
    except Exception as e:
        errors.append(f"integrity_check exception: {e}")

    try:
        rows = conn.execute("PRAGMA foreign_key_check").fetchall()
        if rows:
            for r in rows:
                errors.append(f"FK violation: table={r[0]} rowid={r[1]} parent={r[2]}")
            logger.warning("foreign_key_check: %d violations", len(rows))
    except Exception as e:
        logger.debug("foreign_key_check skipped: %s", e)

    return (len(errors) == 0, errors)


def run_startup_check(conn) -> bool:
    """
    Checks run on app startup.
    Returns False if critical errors found (app should warn user).
    """
    ok, errors = check_integrity(conn)
    if not ok:
        logger.critical("BD CORRUPTA — %d errores: %s", len(errors), errors[:3])
    return ok
