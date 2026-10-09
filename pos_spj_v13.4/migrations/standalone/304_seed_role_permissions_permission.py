"""304 — Permiso para administrar los permisos de los roles (2026-10-04).

Configuración → Usuarios y Roles → Permisos estrena el código
`CONFIGURACION.rol.permisos` (dar o quitar permisos a un rol). Lo recibe el
dueño de la instalación (`system_owner`); los roles administradores ya lo
tienen por el comodín `*`. Nadie más: es el permiso que controla a todos los
demás. Un rol que no exista se omite. Idempotente.
"""

from __future__ import annotations

import logging

from backend.shared.ids import new_uuid

logger = logging.getLogger("spj.migrations.304")


def run(conn) -> None:
    if conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='rol_permisos'"
                    ).fetchone() is None:
        logger.info("304: sin rol_permisos; nada que sembrar.")
        return
    fila = conn.execute("SELECT id FROM roles WHERE lower(trim(nombre))='system_owner'").fetchone()
    if fila is None:
        logger.info("304: no existe system_owner; nada que sembrar.")
        return
    conn.execute(
        "INSERT OR IGNORE INTO rol_permisos (id, rol_id, modulo, accion, permitido)"
        " VALUES (?,?,'CONFIGURACION','rol.permisos',1)", (new_uuid(), str(fila[0])))
    conn.commit()
    logger.info("304: CONFIGURACION.rol.permisos concedido a system_owner.")


up = run
