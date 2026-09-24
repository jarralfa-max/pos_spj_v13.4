"""271 — siembra los permisos de Procesamiento Cárnico (`PRODUCCION.*`) por rol.

POR QUÉ (medido el 2026-09-19 en la base real)
----------------------------------------------
Mismo patrón que la 260 (Precios) y la 268 (POS): los permisos finos de Cárnico
son OTORGABLES pero ningún rol los tenía — `rol_permisos` sólo guarda las 5
acciones gruesas del sembrado base. Sólo admin/system_owner operaban, por
comodín de rol; almacén y gerente no podían ni crear una orden.

REPARTO — decisión del usuario: "almacén produce, gerente aprueba"
----------------------------------------------------------------
- almacen: crear, liberar, ejecutar, completar y cerrar órdenes; capturar
  consumo, pesos y salidas; registrar calidad; aprobar un rendimiento DENTRO
  de tolerancia; pedir el caso de merma; consultar.
- gerente, admin y system_owner: TODO, incluidos aprobar órdenes, aprobar un
  rendimiento FUERA de tolerancia (`rendimiento.sobrescribir`) y producir sin
  existencia de la entrada (`consumo.sobrescribir`).

Un rol inexistente se OMITE. `INSERT OR IGNORE`: no pisa ni revoca nada.
"""

from __future__ import annotations

import logging

from backend.shared.ids import new_uuid

logger = logging.getLogger("spj.migrations.271")

MODULO = "PRODUCCION"

#: Todo el vocabulario de `meat_processing/permissions.py`, sin el prefijo.
#: Transcrito (foto fija); el test lo compara contra ALL_MEAT_PROCESSING_PERMISSIONS.
_TODAS = tuple("""
acceso alerta.enviar alertas.ver analisis.ver bascula.gestionar calidad.registrar_decision
calidad.solicitar_inspeccion calidad.ver configuracion.editar configuracion.ver
consumo.capturar consumo.sobrescribir dashboard.ver derivados.ver despiece.ver
empaque.ejecutar empaque_etiquetado.ver en_proceso.ver equipo.asignar equipo.gestionar
equipo.liberar equipo.mantenimiento equipo.ver etiqueta.imprimir etiqueta.reimprimir
exportar incidencia.reportar incidencia.resolver incidencias.ver lotes_producidos.ver
material.asignar material.sustituir material.ver merma.solicitar notificacion.gestionar
operario.asignar operario.liberar orden.aprobar orden.cancelar orden.cerrar
orden.completar orden.crear orden.editar orden.iniciar orden.liberar orden.pausar
orden.reanudar orden.reversar orden.ver output.capturar output.coproducto.capturar
output.derivado.capturar output.merma.capturar output.subproducto.capturar output.ver
peso.capturar peso.capturar_manual peso.ver plan.aprobar plan.cancelar plan.crear
plan.editar plan.ver preparacion.ver recurso.gestionar recurso.ver rendimiento.aprobar
rendimiento.revisar rendimiento.sobrescribir rendimiento.ver reproceso.aprobar
reproceso.cerrar reproceso.crear reproceso.ejecutar reproceso.ver sacrificio.acceso
sacrificio.ante_mortem.registrar sacrificio.canal.clasificar sacrificio.canal.crear
sacrificio.decomiso.registrar sacrificio.ejecutar sacrificio.enfriamiento.gestionar
sacrificio.lote_animal.gestionar sacrificio.orden.aprobar sacrificio.orden.crear
sacrificio.post_mortem.registrar sacrificio.recepcion_animal trazabilidad.ver ver
ver.auditoria ver.sucursal_propia ver.sucursales_asignadas ver.todas_sucursales
whatsapp.gestionar
""".split())

_ALMACEN = tuple("""
acceso ver ver.sucursal_propia dashboard.ver alertas.ver orden.ver orden.crear
orden.liberar orden.iniciar orden.pausar orden.reanudar orden.completar orden.cerrar
preparacion.ver en_proceso.ver material.ver consumo.capturar peso.ver peso.capturar
output.ver output.capturar output.coproducto.capturar output.subproducto.capturar
output.derivado.capturar output.merma.capturar calidad.ver calidad.registrar_decision
despiece.ver derivados.ver lotes_producidos.ver rendimiento.ver rendimiento.revisar
rendimiento.aprobar merma.solicitar trazabilidad.ver incidencia.reportar incidencias.ver
empaque.ejecutar empaque_etiquetado.ver etiqueta.imprimir configuracion.ver
""".split())

_ASIGNACIONES = {
    "system_owner": _TODAS, "admin": _TODAS, "gerente": _TODAS, "almacen": _ALMACEN,
}


def _tabla_existe(conn, nombre: str) -> bool:
    return conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
                        (nombre,)).fetchone() is not None


def _rol_id(conn, nombre: str) -> str | None:
    fila = conn.execute("SELECT id FROM roles WHERE lower(trim(nombre))=?",
                        (nombre.strip().lower(),)).fetchone()
    return None if fila is None else str(fila[0])


def run(conn) -> None:
    if not (_tabla_existe(conn, "roles") and _tabla_existe(conn, "rol_permisos")):
        logger.info("271: sin tablas de roles/permisos; nada que sembrar.")
        return
    concedidos, omitidos = 0, []
    for rol, acciones in _ASIGNACIONES.items():
        rol_id = _rol_id(conn, rol)
        if rol_id is None:
            omitidos.append(rol)
            continue
        for accion in acciones:
            cur = conn.execute(
                "INSERT OR IGNORE INTO rol_permisos (id, rol_id, modulo, accion, permitido) "
                "VALUES (?,?,?,?,1)", (new_uuid(), rol_id, MODULO, accion))
            concedidos += cur.rowcount if cur.rowcount and cur.rowcount > 0 else 0
    conn.commit()
    logger.info("271: %s permisos PRODUCCION concedidos; roles ausentes: %s",
                concedidos, omitidos or "ninguno")


up = run
