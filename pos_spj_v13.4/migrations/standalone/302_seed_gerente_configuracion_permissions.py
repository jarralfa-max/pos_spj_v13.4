"""302 — `gerente` ve Configuración y gestiona dispositivos (2026-10-04).

POR QUÉ HACE FALTA
------------------
Hasta esta versión la shell viva no filtraba el menú interno de Configuración
por permisos: cualquiera con `CONFIGURACION.ver` veía las once secciones. Al
cerrar ese hueco quedó a la vista que a `gerente` nunca se le sembraron los
permisos granulares de lectura, así que pasaba de ver todo (por el hueco) a ver
sólo «General». Es el patrón otorgable ≠ otorgado de la 260 y la 290.

ALCANCE (decisión del usuario, 2026-10-04)
-----------------------------------------
* `gerente`: LECTURA de todas las secciones, y la gestión operativa del
  mostrador: registrar y editar dispositivos, asignarlos a estaciones y
  gestionar las rutas de impresión. No toca usuarios, roles, secretos,
  integraciones, feature flags, plantillas, temas ni campañas.
* Los demás roles no cambian. Un rol que no exista se OMITE, nunca se crea.
"""

from __future__ import annotations

import logging

from backend.shared.ids import new_uuid

logger = logging.getLogger("spj.migrations.302")

#: Foto fija del día en que corrió (códigos de
#: `backend/application/configuracion/permissions.py`). La prueba que la
#: acompaña verifica que todos sigan existiendo.
GERENTE_CODES = (
    # lectura de cada sección y sus tarjetas
    "CONFIGURACION.empresa.ver", "CONFIGURACION.sucursal.ver", "CONFIGURACION.estacion.ver",
    "DISPOSITIVOS.ver", "DOCUMENTOS.plantilla.ver", "DOCUMENTOS.campana.ver",
    "PANTALLA_CLIENTE.ver", "PANTALLA_CLIENTE.contenido.ver", "PANTALLA_CLIENTE.metricas.ver",
    "CONFIGURACION.integracion.ver", "CONFIGURACION.flag.ver", "CONFIGURACION.apariencia.ver",
    "CONFIGURACION.notificacion.ver", "CONFIGURACION.offline.ver", "CONFIGURACION.usuario.ver",
    "CONFIGURACION.rol.ver", "CONFIGURACION.auditoria.ver",
    # gestión operativa de dispositivos
    "DISPOSITIVOS.crear", "DISPOSITIVOS.editar", "DISPOSITIVOS.asignar",
    "DISPOSITIVOS.configuracion.gestionar",
)


def _tabla_existe(conn, nombre: str) -> bool:
    return conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (nombre,)
    ).fetchone() is not None


def run(conn) -> None:
    if not (_tabla_existe(conn, "roles") and _tabla_existe(conn, "rol_permisos")):
        logger.info("302: sin tablas de roles/permisos; nada que sembrar.")
        return
    fila = conn.execute("SELECT id FROM roles WHERE lower(trim(nombre))='gerente'").fetchone()
    if fila is None:
        logger.info("302: no existe el rol gerente; nada que sembrar.")
        return
    concedidos = 0
    for code in GERENTE_CODES:
        modulo, accion = code.split(".", 1)
        cur = conn.execute(
            "INSERT OR IGNORE INTO rol_permisos (id, rol_id, modulo, accion, permitido) "
            "VALUES (?,?,?,?,1)", (new_uuid(), str(fila[0]), modulo, accion))
        concedidos += max(cur.rowcount or 0, 0)
    conn.commit()
    logger.info("302: %s permisos de Configuración concedidos a gerente.", concedidos)


up = run
