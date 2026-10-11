"""324 — siembra los permisos granulares de `PRODUCTOS` en `rol_permisos`.

POR QUÉ HACE FALTA (re-auditoría PROD-22, medido en la base real)
-----------------------------------------------------------------
Los 68 códigos de `backend/application/products/permissions.py` estaban
registrados en el catálogo (OTORGABLES desde Configuración) pero no otorgados a
nadie: cada rol sólo tenía los gruesos `ver/crear/editar/eliminar/exportar`.
Todo lo decidía el puente de permisos, que concedía aprobar/activar con
`editar` y cualquier código sin mapeo con la sola vista (cajero y
solo_lectura podían, por ejemplo, habilitar productos por sucursal). El puente
ahora sólo traduce lo que el permiso grueso significa; lo sensible exige su
código granular, y esta migración se lo da a quien le corresponde.

MATRIZ (misma regla que Precios, migración 260)
-----------------------------------------------
* `system_owner` y `admin`: todo.
* `gerente`: todo lo operativo, INCLUIDO aprobar y activar. La segregación de
  funciones compara IDENTIDADES: un gerente sigue sin poder aprobar su propia
  receta, pero otro sí. Queda fuera la configuración del módulo y sus alertas
  (`configuracion.editar`, `notificacion.gestionar`, `whatsapp.gestionar`,
  `codigo.configurar_reglas`).
* `almacen`: captura y mantenimiento técnico (internos, clasificación cárnica,
  borradores de receta/rendimiento/despiece) — nunca aprobar, activar,
  bloquear, descontinuar ni habilitar por sucursal.
* `cajero` y `solo_lectura`: nada nuevo; su `PRODUCTOS.ver` ya les da la
  consulta a través del puente.

Un rol que no exista se OMITE, nunca se crea. Sólo `INSERT OR IGNORE`
(`rol_permisos` tiene UNIQUE(rol_id, modulo, accion)): idempotente y nunca
revoca lo que alguien ya haya concedido a mano.
"""

from __future__ import annotations

import logging

from backend.shared.ids import new_uuid

logger = logging.getLogger("spj.migrations.324")

MODULO = "PRODUCTOS"

#: Foto fija de las acciones de `ProductPermissions` el día que corrió; el test
#: que acompaña la migración la compara contra `ALL_PRODUCT_PERMISSIONS`.
_TODAS = (
    "acceso", "ver", "ver.costo_referencia", "ver.interno", "ver.carnico",
    "ver.auditoria", "exportar",
    "crear", "editar", "enviar_revision", "aprobar", "activar", "bloquear",
    "eliminar", "descontinuar", "archivar",
    "codigo.sobrescribir", "codigo.configurar_reglas",
    "categoria.ver", "categoria.gestionar",
    "marca.ver", "marca.gestionar",
    "atributo.ver", "atributo.gestionar", "variante.generar",
    "imagen.gestionar",
    "combo.ver", "combo.gestionar",
    "especie.ver", "especie.gestionar",
    "clasificacion_carnica.ver", "clasificacion_carnica.gestionar",
    "corte.ver", "corte.gestionar",
    "unidad.ver", "unidad.gestionar", "conversion.gestionar",
    "codigo_barras.gestionar", "codigo_alterno.gestionar",
    "receta.ver", "receta.crear", "receta.editar", "receta.aprobar", "receta.activar",
    "rendimiento.ver", "rendimiento.crear", "rendimiento.editar",
    "rendimiento.aprobar", "rendimiento.activar",
    "despiece.ver", "despiece.gestionar",
    "interno.ver", "interno.crear", "interno.editar", "interno.activar",
    "sucursal.ver", "sucursal.gestionar", "surtido.gestionar",
    "externo.buscar", "externo.importar", "externo.revisar", "externo.aprobar",
    "importacion.ejecutar", "importacion.aprobar",
    "configuracion.ver", "configuracion.editar",
    "notificacion.gestionar", "whatsapp.gestionar",
)

_SOLO_CONFIGURACION = {
    "configuracion.editar", "notificacion.gestionar", "whatsapp.gestionar",
    "codigo.configurar_reglas",
}
_GERENTE = tuple(a for a in _TODAS if a not in _SOLO_CONFIGURACION)

_ALMACEN = (
    "acceso", "ver", "ver.interno", "ver.carnico", "exportar",
    "crear", "editar", "enviar_revision",
    "categoria.ver", "categoria.gestionar", "marca.ver", "marca.gestionar",
    "atributo.ver", "atributo.gestionar", "variante.generar", "imagen.gestionar",
    "combo.ver", "combo.gestionar",
    "especie.ver", "clasificacion_carnica.ver", "clasificacion_carnica.gestionar",
    "corte.ver", "corte.gestionar",
    "unidad.ver", "unidad.gestionar", "conversion.gestionar",
    "codigo_barras.gestionar", "codigo_alterno.gestionar",
    "receta.ver", "receta.crear", "receta.editar",
    "rendimiento.ver", "rendimiento.crear", "rendimiento.editar",
    "despiece.ver", "despiece.gestionar",
    "interno.ver", "interno.crear", "interno.editar",
    "sucursal.ver", "externo.buscar", "importacion.ejecutar",
    "configuracion.ver",
)

ASIGNACIONES: dict[str, tuple[str, ...]] = {
    "system_owner": _TODAS,
    "admin": _TODAS,
    "gerente": _GERENTE,
    "almacen": _ALMACEN,
}


def _tabla_existe(conn, nombre: str) -> bool:
    return conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (nombre,)
    ).fetchone() is not None


def _rol_id(conn, nombre: str) -> str | None:
    fila = conn.execute(
        "SELECT id FROM roles WHERE lower(trim(nombre))=?", (nombre.strip().lower(),)
    ).fetchone()
    return None if fila is None else str(fila[0])


def run(conn) -> None:
    if not (_tabla_existe(conn, "roles") and _tabla_existe(conn, "rol_permisos")):
        logger.info("324: sin tablas de roles/permisos; nada que sembrar.")
        return
    concedidos, omitidos = 0, []
    for rol, acciones in ASIGNACIONES.items():
        rol_id = _rol_id(conn, rol)
        if rol_id is None:
            omitidos.append(rol)
            continue
        for accion in acciones:
            cur = conn.execute(
                "INSERT OR IGNORE INTO rol_permisos (id, rol_id, modulo, accion, permitido) "
                "VALUES (?,?,?,?,1)", (new_uuid(), rol_id, MODULO, accion))
            concedidos += cur.rowcount or 0
    conn.commit()
    logger.info("324: %d permisos de PRODUCTOS sembrados; roles omitidos: %s",
                concedidos, omitidos or "ninguno")


up = run
