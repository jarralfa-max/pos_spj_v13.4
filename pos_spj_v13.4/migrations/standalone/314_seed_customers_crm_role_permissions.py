"""314 — siembra las acciones granulares de Clientes y CRM en `rol_permisos`.

POR QUÉ HACE FALTA (medido en una copia de la base viva el 2026-10-08)
-------------------------------------------------------------------
Clientes y CRM declara 180 acciones (`backend/application/customers/
permissions.py` + `backend/application/crm/permissions.py`), todas otorgables
desde la matriz de permisos, pero los roles sólo traían los códigos gruesos del
módulo viejo (`CLIENTES.ver/crear/editar/eliminar/exportar`). El dueño y el
administrador entraban porque el evaluador de sesión les da paso libre por rol;
cualquier otro usuario veía «No tienes permiso» (el módulo exige
`CLIENTES.acceso`), y la entrada del menú (`CLIENTES_CRM.ver`) no la tenía
NINGÚN rol. Además el POS busca clientes con `CLIENTES.buscar`: un cajero no
podía ponerle cliente a una venta.

ALCANCE (decisión del usuario, 2026-10-08 — «matriz completa»)
---------------------------------------------------------------
* `system_owner` y `admin`: TODO.
* `gerente`: supervisor comercial + supervisor de atención + gerente de
  crédito. Ve prospectos, oportunidades y casos de SU SUCURSAL; asigna,
  reasigna, mueve etapas, gana/pierde, escala, resuelve; solicita, revisa y
  APRUEBA crédito (nunca su propia solicitud: lo impide la segregación de
  funciones del caso de uso, no el rol); duplicados, calidad e importación.
  Fuera: configuración del módulo (pipelines, SLA, automatizaciones,
  retención), anonimizar y desenmascarar/exportar datos sensibles.
* `cajero`: busca, da de alta y edita datos básicos de clientes; contactos,
  direcciones, datos fiscales, consentimientos y preferencias; registra
  quejas/casos (ve los suyos), notas y seguimientos propios.
* `solo_lectura`: consulta sin datos sensibles (sucursal).
* `almacen`, `repartidor`: nada.

Clientes globales para todos (decisión del usuario): `CLIENTES.ver.compania`.
Prospectos/oportunidades/casos: gerente `ver.sucursal`, cajero `ver.propia`.

Borra `CLIENTES.eliminar`: no existe en el catálogo (nadie lo comprueba; la
baja reversible es `CLIENTES.desactivar`) y la matriz no puede mostrarlo.

Un rol que no exista se OMITE, nunca se crea.
"""

from __future__ import annotations

import logging

from backend.shared.ids import new_uuid

logger = logging.getLogger("spj.migrations.314")

#: Foto fija de `ALL_CUSTOMER_PERMISSIONS | ALL_CRM_PERMISSIONS` el día que
#: corrió. El test que la acompaña la compara contra el catálogo vivo.
_CLIENTES = (
    "acceso", "dashboard.ver", "buscar", "buscar.global", "configuracion.ver",
    "configuracion.editar", "auditoria.ver",
    "ver", "ver.propia", "ver.equipo", "ver.sucursal", "ver.territorio", "ver.cartera",
    "ver.compania", "crear", "editar", "editar.propia", "editar.sensible", "activar",
    "desactivar", "suspender", "bloquear", "cerrar", "reabrir", "anonimizar",
    "contacto.ver", "contacto.crear", "contacto.editar", "contacto.eliminar",
    "contacto.verificar", "contacto.marcar_principal",
    "direccion.ver", "direccion.crear", "direccion.editar", "direccion.eliminar",
    "direccion.marcar_predeterminada",
    "fiscal.ver", "fiscal.editar", "fiscal.validar",
    "credito.ver", "credito.ver_resumen", "credito.ver_sensible", "credito.solicitar",
    "credito.revisar", "credito.aprobar", "credito.rechazar", "credito.limite.editar",
    "credito.limite.sobrescribir", "credito.suspender", "credito.bloquear",
    "credito.cerrar", "credito.reabrir", "credito.historial.ver", "credito.exportar",
    "consentimiento.ver", "consentimiento.capturar", "consentimiento.retirar",
    "consentimiento.evidencia.ver",
    "preferencia_comunicacion.ver", "preferencia_comunicacion.gestionar",
    "privacidad.solicitud.ver", "privacidad.solicitud.crear",
    "privacidad.solicitud.procesar", "privacidad.solicitud.aprobar",
    "sensible.ver", "sensible.exportar", "sensible.desenmascarar",
    "calidad.ver", "calidad.resolver",
    "duplicados.ver", "duplicados.revisar", "duplicados.descartar", "duplicados.fusionar",
    "importar", "importar.aprobar", "exportar", "actualizacion_masiva",
    "elegibilidad_comercial.verificar", "pedidos.ver", "entregas.ver", "fidelidad.ver",
    "whatsapp.ver", "sync_conflictos.ver", "sync_conflictos.resolver",
)

_CRM = (
    "leads.ver", "leads.ver.propia", "leads.ver.equipo", "leads.ver.sucursal",
    "leads.ver.compania", "leads.crear", "leads.editar", "leads.asignar",
    "leads.reasignar", "leads.calificar", "leads.descalificar", "leads.convertir",
    "leads.archivar", "leads.exportar",
    "oportunidades.ver", "oportunidades.ver.propia", "oportunidades.ver.equipo",
    "oportunidades.ver.sucursal", "oportunidades.ver.compania", "oportunidades.crear",
    "oportunidades.editar", "oportunidades.asignar", "oportunidades.reasignar",
    "oportunidades.cambiar_etapa", "oportunidades.sobrescribir_etapa",
    "oportunidades.marcar_ganada", "oportunidades.marcar_perdida",
    "oportunidades.reabrir", "pipeline.ver", "pipeline.configurar", "forecast.ver",
    "forecast.ver.equipo", "forecast.ver.compania",
    "actividades.ver", "actividades.crear", "actividades.editar", "actividades.completar",
    "actividades.cancelar", "actividades.reasignar",
    "tareas.ver", "tareas.crear", "tareas.asignar", "tareas.reasignar", "tareas.completar",
    "tareas.cancelar", "tareas.reprogramar",
    "notas.ver", "notas.crear", "notas.editar.propia", "notas.eliminar.propia",
    "notas.ver.privada", "notas.crear.privada", "recordatorios.crear",
    "casos.ver", "casos.ver.propia", "casos.ver.equipo", "casos.ver.sucursal",
    "casos.ver.compania", "casos.crear", "casos.editar", "casos.asignar",
    "casos.reasignar", "casos.escalar", "casos.resolver", "casos.cerrar", "casos.reabrir",
    "casos.ver.sensible", "sla.ver", "sla.gestionar", "sla.sobrescribir",
    "segmentos.ver", "segmentos.crear", "segmentos.editar", "segmentos.asignar",
    "segmentos.remover", "etiquetas.ver", "etiquetas.crear", "etiquetas.editar",
    "etiquetas.asignar", "etiquetas.remover", "territorios.ver", "territorios.gestionar",
    "carteras.ver", "carteras.gestionar", "carteras.asignar",
    "propietario.ver", "propietario.asignar", "propietario.reasignar",
    "bi.exportar",
    "automatizaciones.ver", "automatizaciones.crear", "automatizaciones.editar",
    "automatizaciones.activar", "automatizaciones.desactivar",
    "automatizaciones.ver_ejecuciones",
    "sync_conflictos.ver", "sync_conflictos.resolver",
)

# ── cajero ───────────────────────────────────────────────────────────────
_CAJERO_CLIENTES = (
    "acceso", "dashboard.ver", "buscar", "ver", "ver.compania", "crear", "editar",
    "contacto.ver", "contacto.crear", "contacto.editar", "contacto.marcar_principal",
    "direccion.ver", "direccion.crear", "direccion.editar",
    "direccion.marcar_predeterminada",
    "fiscal.ver", "fiscal.editar",
    "consentimiento.ver", "consentimiento.capturar", "consentimiento.retirar",
    "preferencia_comunicacion.ver", "preferencia_comunicacion.gestionar",
    "credito.ver_resumen", "elegibilidad_comercial.verificar",
    "pedidos.ver", "entregas.ver", "fidelidad.ver", "whatsapp.ver",
)
_CAJERO_CRM = (
    "casos.ver", "casos.ver.propia", "casos.crear", "casos.editar",
    "notas.ver", "notas.crear", "notas.editar.propia", "notas.eliminar.propia",
    "actividades.ver", "actividades.crear", "actividades.completar",
    "tareas.ver", "tareas.crear", "tareas.completar", "tareas.reprogramar",
    "recordatorios.crear", "sla.ver",
)

# ── gerente (además de lo del cajero) ──────────────────────────────────────
_GERENTE_EXTRA_CLIENTES = (
    "buscar.global", "configuracion.ver", "auditoria.ver", "ver.sucursal",
    "editar.sensible", "activar", "desactivar", "suspender", "bloquear", "cerrar", "reabrir",
    "contacto.eliminar", "contacto.verificar", "direccion.eliminar", "fiscal.validar",
    "credito.ver", "credito.ver_sensible", "credito.solicitar", "credito.revisar",
    "credito.aprobar", "credito.rechazar", "credito.limite.editar",
    "credito.limite.sobrescribir", "credito.suspender", "credito.bloquear",
    "credito.cerrar", "credito.reabrir", "credito.historial.ver", "credito.exportar",
    "consentimiento.evidencia.ver",
    "privacidad.solicitud.ver", "privacidad.solicitud.crear", "privacidad.solicitud.procesar",
    "sensible.ver",
    "calidad.ver", "calidad.resolver",
    "duplicados.ver", "duplicados.revisar", "duplicados.descartar", "duplicados.fusionar",
    "importar", "importar.aprobar", "exportar",
    "sync_conflictos.ver", "sync_conflictos.resolver",
)
_GERENTE_EXTRA_CRM = (
    "leads.ver", "leads.ver.propia", "leads.ver.sucursal", "leads.crear", "leads.editar",
    "leads.asignar", "leads.reasignar", "leads.calificar", "leads.descalificar",
    "leads.convertir", "leads.archivar", "leads.exportar",
    "oportunidades.ver", "oportunidades.ver.propia", "oportunidades.ver.sucursal",
    "oportunidades.crear", "oportunidades.editar", "oportunidades.asignar",
    "oportunidades.reasignar", "oportunidades.cambiar_etapa",
    "oportunidades.sobrescribir_etapa", "oportunidades.marcar_ganada",
    "oportunidades.marcar_perdida", "oportunidades.reabrir",
    "pipeline.ver", "forecast.ver", "forecast.ver.equipo",
    "actividades.editar", "actividades.cancelar", "actividades.reasignar",
    "tareas.asignar", "tareas.reasignar", "tareas.cancelar",
    "notas.ver.privada", "notas.crear.privada",
    "casos.ver.sucursal", "casos.asignar", "casos.reasignar", "casos.escalar",
    "casos.resolver", "casos.cerrar", "casos.reabrir", "casos.ver.sensible",
    "sla.sobrescribir",
    "segmentos.ver", "segmentos.crear", "segmentos.editar", "segmentos.asignar",
    "segmentos.remover", "etiquetas.ver", "etiquetas.crear", "etiquetas.editar",
    "etiquetas.asignar", "etiquetas.remover", "territorios.ver", "carteras.ver",
    "carteras.asignar", "propietario.ver", "propietario.asignar", "propietario.reasignar",
    "automatizaciones.ver", "automatizaciones.ver_ejecuciones",
    "sync_conflictos.ver", "sync_conflictos.resolver",
)

# ── solo lectura ───────────────────────────────────────────────────────────
_LECTURA_CLIENTES = (
    "acceso", "dashboard.ver", "buscar", "ver", "ver.compania",
    "contacto.ver", "direccion.ver", "fiscal.ver", "consentimiento.ver",
    "preferencia_comunicacion.ver", "credito.ver_resumen", "calidad.ver",
    "duplicados.ver", "pedidos.ver", "entregas.ver", "fidelidad.ver", "whatsapp.ver",
)
_LECTURA_CRM = (
    "leads.ver", "leads.ver.sucursal", "oportunidades.ver", "oportunidades.ver.sucursal",
    "pipeline.ver", "forecast.ver", "actividades.ver", "tareas.ver", "notas.ver",
    "casos.ver", "casos.ver.sucursal", "sla.ver", "segmentos.ver", "etiquetas.ver",
    "territorios.ver", "carteras.ver", "propietario.ver",
)

_ASIGNACIONES: dict[str, dict[str, tuple[str, ...]]] = {
    "system_owner": {"CLIENTES": _CLIENTES, "CRM": _CRM, "CLIENTES_CRM": ("ver",)},
    "admin": {"CLIENTES": _CLIENTES, "CRM": _CRM, "CLIENTES_CRM": ("ver",)},
    "gerente": {"CLIENTES": _CAJERO_CLIENTES + _GERENTE_EXTRA_CLIENTES,
                "CRM": _CAJERO_CRM + _GERENTE_EXTRA_CRM, "CLIENTES_CRM": ("ver",)},
    "cajero": {"CLIENTES": _CAJERO_CLIENTES, "CRM": _CAJERO_CRM, "CLIENTES_CRM": ("ver",)},
    "solo_lectura": {"CLIENTES": _LECTURA_CLIENTES, "CRM": _LECTURA_CRM,
                     "CLIENTES_CRM": ("ver",)},
}

#: Código grueso del módulo viejo: no está en el catálogo y nadie lo comprueba.
_LEGACY = ("eliminar",)


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
        logger.info("314: sin tablas de roles/permisos; nada que sembrar.")
        return
    borrados = conn.execute(
        "DELETE FROM rol_permisos WHERE upper(modulo)='CLIENTES' AND lower(accion) IN (?)",
        _LEGACY,
    ).rowcount or 0
    concedidos, omitidos = 0, []
    for rol, por_modulo in _ASIGNACIONES.items():
        rol_id = _rol_id(conn, rol)
        if rol_id is None:
            omitidos.append(rol)
            continue
        for modulo, acciones in por_modulo.items():
            ya = {
                str(fila[0]).lower()
                for fila in conn.execute(
                    "SELECT accion FROM rol_permisos WHERE rol_id=? AND upper(modulo)=?",
                    (rol_id, modulo),
                )
            }
            for accion in dict.fromkeys(acciones):
                if accion.lower() in ya:
                    continue
                conn.execute(
                    "INSERT INTO rol_permisos (id, rol_id, modulo, accion, permitido) "
                    "VALUES (?,?,?,?,1)",
                    (new_uuid(), rol_id, modulo, accion),
                )
                concedidos += 1
    conn.commit()
    logger.info("314: %s permisos de Clientes/CRM concedidos, %s gruesos borrados; "
                "roles omitidos: %s", concedidos, borrados, omitidos or "ninguno")


up = run
