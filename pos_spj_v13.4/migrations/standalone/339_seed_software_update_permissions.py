"""339 — permisos de «Acerca de y actualizaciones» (2026-10-14).

`CONFIGURACION.actualizacion.ver`, `.administrar` y `.canal` nacen con el
actualizador. Sin sembrarlos, la sección sólo la vería el administrador
(otorgable no es otorgado). Se siembran POR FUNCIÓN:

* ``system_owner`` y ``admin`` — las tres (instalan software en la estación);
* ``gerente`` y ``solo_lectura`` — sólo ver (versión, canal, historial; nunca
  secretos ni acciones).

Instalar sigue exigiendo además la autorización de administrador de Windows
(UAC) en la estación. Abrir o cerrar acciones a otros roles se hace desde
Configuración → Usuarios y Roles → Permisos. Idempotente.
"""

from __future__ import annotations

import logging

from backend.shared.ids import new_uuid

logger = logging.getLogger("spj.migrations.339")

_ADMIN_ACTIONS = ("actualizacion.ver", "actualizacion.administrar", "actualizacion.canal")
_VIEW_ACTIONS = ("actualizacion.ver",)
_PLAN = {
    "system_owner": _ADMIN_ACTIONS,
    "admin": _ADMIN_ACTIONS,
    "gerente": _VIEW_ACTIONS,
    "solo_lectura": _VIEW_ACTIONS,
}


def _tabla(conn, nombre: str) -> bool:
    return conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
                        (nombre,)).fetchone() is not None


def run(conn) -> None:
    if not (_tabla(conn, "roles") and _tabla(conn, "rol_permisos")):
        logger.info("339: sin tablas de roles; nada que sembrar.")
        return
    concedidos, omitidos = 0, []
    for rol, acciones in _PLAN.items():
        fila = conn.execute("SELECT id FROM roles WHERE lower(trim(nombre))=?",
                            (rol,)).fetchone()
        if fila is None:
            omitidos.append(rol)
            continue
        rol_id = str(fila[0])
        ya = {str(r[0]).lower() for r in conn.execute(
            "SELECT accion FROM rol_permisos WHERE rol_id=? AND upper(modulo)='CONFIGURACION'",
            (rol_id,))}
        for accion in acciones:
            if accion in ya:
                continue
            conn.execute("INSERT INTO rol_permisos (id, rol_id, modulo, accion, permitido)"
                         " VALUES (?,?,?,?,1)", (new_uuid(), rol_id, "CONFIGURACION", accion))
            concedidos += 1
    conn.commit()
    logger.info("339: %s permisos de actualizaciones concedidos; roles omitidos: %s",
                concedidos, omitidos or "ninguno")


up = run
