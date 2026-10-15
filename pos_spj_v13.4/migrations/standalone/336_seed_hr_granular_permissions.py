"""336 — permisos granulares de RR. HH. (auditoría cebf67a HR-01, 2026-10-14).

Cada comando de RR. HH. exige ahora su ``RRHH.<accion>`` y la política falla
cerrada. Antes NINGÚN comando consultaba permisos, así que quien entraba al
módulo (``RRHH.ver``) podía todo. Se siembra POR FUNCIÓN, sobre los roles que ya
tenían RRHH en el sembrado base:

* ``system_owner``, ``admin`` y ``gerente`` — todas las acciones (ya tenían
  ``RRHH`` crear/editar/eliminar, es decir, operaban el módulo completo). La
  separación de funciones no depende del rol: quien genera una nómina no la
  autoriza y nadie aprueba su propia ausencia o ajuste (se comparan identidades).
* ``solo_lectura`` — sólo las de consulta.

Las acciones gruesas previas de ``RRHH`` quedan inertes (el catálogo granular
las sustituye, como hizo Inventario en la 179). Abrir o cerrar acciones a otros
roles se hace desde Configuración → Seguridad → Permisos. Idempotente.
"""

from __future__ import annotations

import logging

from backend.shared.ids import new_uuid

logger = logging.getLogger("spj.migrations.336")

_FULL_ROLES = ("system_owner", "admin", "gerente")
_READ_ROLES = ("solo_lectura",)


def _tabla(conn, nombre: str) -> bool:
    return conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
                        (nombre,)).fetchone() is not None


def run(conn) -> None:
    if not (_tabla(conn, "roles") and _tabla(conn, "rol_permisos")):
        logger.info("336: sin tablas de roles; nada que sembrar.")
        return
    from backend.application.hr.permissions import (
        ALL_HR_PERMISSIONS,
        HR_READ_ONLY_PERMISSIONS,
    )

    plan = {rol: ALL_HR_PERMISSIONS for rol in _FULL_ROLES}
    plan.update({rol: HR_READ_ONLY_PERMISSIONS for rol in _READ_ROLES})
    concedidos, omitidos = 0, []
    for rol, codigos in plan.items():
        fila = conn.execute("SELECT id FROM roles WHERE lower(trim(nombre))=?",
                            (rol,)).fetchone()
        if fila is None:
            omitidos.append(rol)
            continue
        rol_id = str(fila[0])
        ya = {str(r[0]).lower() for r in conn.execute(
            "SELECT accion FROM rol_permisos WHERE rol_id=? AND upper(modulo)='RRHH'",
            (rol_id,))}
        for accion in sorted(code.split(".", 1)[1] for code in codigos):
            if accion.lower() in ya:
                continue
            conn.execute("INSERT INTO rol_permisos (id, rol_id, modulo, accion, permitido)"
                         " VALUES (?,?,?,?,1)", (new_uuid(), rol_id, "RRHH", accion))
            concedidos += 1
    conn.commit()
    logger.info("336: %s permisos de RR. HH. concedidos; roles omitidos: %s",
                concedidos, omitidos or "ninguno")


up = run
