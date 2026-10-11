"""319 — permisos de Cotizaciones por rol (CRM-43, 2026-10-09).

DECISIÓN DEL USUARIO («como el CRM»)
------------------------------------
* Dueño/admin: todo, toda la empresa.
* Gerente: las de su sucursal; crea, edita, aprueba, envía, registra respuesta,
  cancela, convierte en pedido y exporta.
* Cajero: las suyas; crea, edita, envía, registra respuesta, cancela, convierte
  y exporta. No aprueba.
* Solo lectura: consulta las de su sucursal.
* Almacén / repartidor: nada.

El módulo ``COTIZACIONES`` ya existía en ``rol_permisos`` con las acciones
gruesas del sembrado base; ``eliminar`` se retira (una cotización se cancela,
nunca se borra; ningún caso de uso lo exige). Idempotente.
"""

from __future__ import annotations

import logging

from backend.shared.ids import new_uuid

logger = logging.getLogger("spj.migrations.319")

_TODO = ("ver", "ver.propia", "ver.sucursal", "ver.compania", "crear", "editar", "aprobar",
         "enviar", "registrar_respuesta", "cancelar", "convertir", "exportar")
_CAJERO = ("ver", "ver.propia", "crear", "editar", "enviar", "registrar_respuesta",
           "cancelar", "convertir", "exportar")
_GERENTE = _CAJERO + ("ver.sucursal", "aprobar")
_LECTURA = ("ver", "ver.sucursal")

_ASIGNACIONES = {"system_owner": _TODO, "admin": _TODO, "gerente": _GERENTE,
                 "cajero": _CAJERO, "solo_lectura": _LECTURA}
_LEGACY = ("eliminar",)


def _tabla(conn, nombre: str) -> bool:
    return conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
                        (nombre,)).fetchone() is not None


def run(conn) -> None:
    if not (_tabla(conn, "roles") and _tabla(conn, "rol_permisos")):
        logger.info("319: sin tablas de roles; nada que sembrar.")
        return
    borrados = conn.execute(
        "DELETE FROM rol_permisos WHERE upper(modulo)='COTIZACIONES' AND lower(accion) IN (?)",
        _LEGACY).rowcount or 0
    concedidos, omitidos = 0, []
    for rol, acciones in _ASIGNACIONES.items():
        fila = conn.execute("SELECT id FROM roles WHERE lower(trim(nombre))=?",
                            (rol,)).fetchone()
        if fila is None:
            omitidos.append(rol)
            continue
        rol_id = str(fila[0])
        ya = {str(r[0]).lower() for r in conn.execute(
            "SELECT accion FROM rol_permisos WHERE rol_id=? AND upper(modulo)='COTIZACIONES'",
            (rol_id,))}
        for accion in acciones:
            if accion in ya:
                continue
            conn.execute("INSERT INTO rol_permisos (id, rol_id, modulo, accion, permitido)"
                         " VALUES (?,?,?,?,1)", (new_uuid(), rol_id, "COTIZACIONES", accion))
            concedidos += 1
    conn.commit()
    logger.info("319: %s permisos de Cotizaciones concedidos, %s gruesos retirados; "
                "roles omitidos: %s", concedidos, borrados, omitidos or "ninguno")


up = run
