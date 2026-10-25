"""348 — Retira las tablas del RBAC heredado (auditoría de permisos 968e0bc, PER-05).

`permisos`, `roles_permisos` y `usuarios_roles` eran el almacén de
`security/rbac.py`, un RBAC paralelo retirado en la misma auditoría. Medido en
la base real (2026-10-23): 0 filas en las tres, ninguna clave foránea, vista ni
trigger que dependa de ellas, y ningún lector ni escritor en el código. El único
consumidor que quedaba (el notificador interno de Pedidos) ya resuelve
destinatarios por `usuarios.rol`.

Prudente con otras instalaciones: si alguna tabla TIENE filas, no se borra
nada y se deja aviso en el log para revisarlo a mano. `m000` ya no las crea.
El corte UUID (migración 200) omite las tablas que no existen.

Idempotente.
"""

from __future__ import annotations

import logging

logger = logging.getLogger("spj.migrations.348")

LEGACY_RBAC_TABLES = ("roles_permisos", "usuarios_roles", "permisos")


def _exists(conn, table: str) -> bool:
    return conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
                        (table,)).fetchone() is not None


def run(conn) -> None:
    presentes = [t for t in LEGACY_RBAC_TABLES if _exists(conn, t)]
    con_filas = {t: conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0] for t in presentes}
    ocupadas = {t: n for t, n in con_filas.items() if n}
    if ocupadas:
        logger.warning("348: el RBAC heredado tiene filas %s; no se retira. Revisar a mano "
                       "(los permisos vigentes viven en rol_permisos).", ocupadas)
        return
    for tabla in presentes:
        conn.execute(f"DROP TABLE {tabla}")
    logger.info("348: tablas del RBAC heredado retiradas: %s", presentes or "ninguna")
