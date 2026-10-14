"""333 — permisos granulares de Finanzas (auditoría d9f2bca F02, 2026-10-10).

Cada comando financiero exige ahora su ``FINANZAS.<accion>``. Se siembran sólo
en ``system_owner`` y ``admin``: hoy ningún otro rol tiene ``FINANZAS.ver`` (el
sembrado base otorga ``FINANZAS_UNIFICADAS``, que el menú no usa), así que nadie
más entraba al módulo. Esta migración NO cambia quién ve Finanzas; sólo hace que
dentro del módulo cada operación pida su permiso. Abrirlo a gerente u otros
roles es decisión del negocio desde Configuración → Seguridad → Permisos.
Idempotente.
"""

from __future__ import annotations

import logging

from backend.shared.ids import new_uuid

logger = logging.getLogger("spj.migrations.333")

_ROLES = ("system_owner", "admin")


def _tabla(conn, nombre: str) -> bool:
    return conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
                        (nombre,)).fetchone() is not None


def run(conn) -> None:
    if not (_tabla(conn, "roles") and _tabla(conn, "rol_permisos")):
        logger.info("333: sin tablas de roles; nada que sembrar.")
        return
    from backend.application.finance.permissions import ALL_FINANCE_PERMISSIONS

    acciones = sorted(code.split(".", 1)[1] for code in ALL_FINANCE_PERMISSIONS)
    concedidos, omitidos = 0, []
    for rol in _ROLES:
        fila = conn.execute("SELECT id FROM roles WHERE lower(trim(nombre))=?",
                            (rol,)).fetchone()
        if fila is None:
            omitidos.append(rol)
            continue
        rol_id = str(fila[0])
        ya = {str(r[0]).lower() for r in conn.execute(
            "SELECT accion FROM rol_permisos WHERE rol_id=? AND upper(modulo)='FINANZAS'",
            (rol_id,))}
        for accion in acciones:
            if accion in ya:
                continue
            conn.execute("INSERT INTO rol_permisos (id, rol_id, modulo, accion, permitido)"
                         " VALUES (?,?,?,?,1)", (new_uuid(), rol_id, "FINANZAS", accion))
            concedidos += 1
    conn.commit()
    logger.info("333: %s permisos de Finanzas concedidos; roles omitidos: %s",
                concedidos, omitidos or "ninguno")


up = run
