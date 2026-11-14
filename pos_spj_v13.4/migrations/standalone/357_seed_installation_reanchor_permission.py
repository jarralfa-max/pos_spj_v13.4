"""357 — permiso para re-anclar la sucursal de la estación (SDLC-ARQ-TERM-002).

`CONFIGURACION.estacion.reanclar` nace con la regla que lo exige en backend
(`SetInstallationBranchUseCase`). Antes bastaba `CONFIGURACION.empresa.editar`,
y sólo lo comprobaba la pantalla.

Se siembra únicamente a ``system_owner`` y ``admin``, los roles de acceso total
(`backend/security/permissions/principals.py`): no amplía lo que nadie podía
hacer ya. Ningún otro rol lo recibe de fábrica (mínimo privilegio,
`docs/sdlc/inputs/requisitos-arquitectura.md` §3); se otorga desde
Configuración → Usuarios y Roles → Permisos. Sólo agrega filas. Idempotente.

Reversa: borrar las filas `CONFIGURACION`/`estacion.reanclar` de `rol_permisos`
y la versión 357 de `schema_migrations`.
"""

from __future__ import annotations

import logging

from backend.shared.ids import new_uuid

logger = logging.getLogger("spj.migrations.357")

_MODULO = "CONFIGURACION"
_ACCION = "estacion.reanclar"
_ROLES = ("system_owner", "admin")


def _tabla(conn, nombre: str) -> bool:
    return conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
                        (nombre,)).fetchone() is not None


def run(conn) -> None:
    if not (_tabla(conn, "roles") and _tabla(conn, "rol_permisos")):
        logger.info("357: sin tablas de roles; nada que sembrar.")
        return
    concedidos, omitidos = 0, []
    for rol in _ROLES:
        fila = conn.execute("SELECT id FROM roles WHERE lower(trim(nombre))=?",
                            (rol,)).fetchone()
        if fila is None:
            omitidos.append(rol)
            continue
        rol_id = str(fila[0])
        ya = conn.execute(
            "SELECT 1 FROM rol_permisos WHERE rol_id=? AND upper(modulo)=? AND lower(accion)=?",
            (rol_id, _MODULO, _ACCION)).fetchone()
        if ya is not None:
            continue
        conn.execute("INSERT INTO rol_permisos (id, rol_id, modulo, accion, permitido)"
                     " VALUES (?,?,?,?,1)", (new_uuid(), rol_id, _MODULO, _ACCION))
        concedidos += 1
    conn.commit()
    logger.info("357: %s permisos de re-anclaje concedidos; roles omitidos: %s",
                concedidos, omitidos or "ninguno")


up = run
