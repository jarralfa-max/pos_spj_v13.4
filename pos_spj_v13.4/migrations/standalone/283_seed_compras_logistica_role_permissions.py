"""283 — siembra las acciones GRANULARES de Compras y Logística por función.

POR QUÉ HACE FALTA
------------------
Medido el 2026-09-30 en la base viva: `rol_permisos` sólo tenía las cinco
acciones gruesas de `COMPRAS` (ver/crear/editar/eliminar/exportar) y CERO de
`LOGISTICA`. Los casos de uso exigen las acciones granulares
(`COMPRAS.orden.aprobar`, `LOGISTICA.embarque.recibir`, …), así que ningún rol
que no fuera administrador podía crear una orden, recibirla ni recibir un
embarque. Además `LOGISTICA` ni siquiera era otorgable desde la matriz de
permisos: no estaba en el catálogo (se añadió con
`backend/application/logistics/permissions.py`).

Es el mismo mecanismo que se pudre y que ya documentó la migración 260: la
migración 206 siembra con una lista de módulos congelada.

ALCANCE DECIDIDO POR EL USUARIO (2026-09-30, «por función»)
-----------------------------------------------------------
* `system_owner` y `admin`: todo (ya lo pueden por ser administradores; se
  siembra igual para que la matriz lo muestre y no dependa del nombre del rol).
* `gerente`: todo Compras y todo Logística.
* `almacen`: ver Compras y órdenes, y RECIBIR — recepción (crear, completar,
  parcial, rechazar, peso manual), llegada y conteo de embarques, escaneo,
  movimiento y liberación de contenedores, etiquetas. Nada de crear órdenes,
  aprobar, facturas ni liberar diferencias.
* `cajero`, `solo_lectura`, `repartidor`: nada.

Un rol que no exista se OMITE, nunca se crea. Las listas se transcriben (foto
fija de la migración); la prueba que la acompaña las compara contra el
vocabulario vivo para detectar erratas.
"""

from __future__ import annotations

import logging

from backend.shared.ids import new_uuid

logger = logging.getLogger("spj.migrations.283")

_COMPRAS = (
    "ver", "ver.sucursal_propia", "ver.sucursales_asignadas", "ver.todas_sucursales",
    "ver.costos", "ver.margenes", "ver.pagos", "ver.credito_proveedor", "ver.auditoria",
    "ver.analitica", "exportar",
    "directa.ver", "directa.crear", "directa.editar", "directa.confirmar",
    "directa.guardar_borrador", "directa.proveedor_ocasional", "directa.crear_producto",
    "directa.sobrescribir_precio", "directa.sobrescribir_costo", "directa.sobre_recibir",
    "directa.cancelar", "directa.reversar", "directa.imprimir",
    "pago.inmediato", "pago.caja_chica", "pago.tesoreria", "pago.transferencia",
    "credito_proveedor.usar", "anticipo.usar", "condiciones.mixtas", "limite.sobrescribir",
    "pago.ver_referencia",
    "solicitud.ver", "solicitud.crear", "solicitud.editar", "solicitud.enviar",
    "solicitud.aprobar", "solicitud.rechazar", "solicitud.cancelar",
    "rfq.crear", "rfq.enviar",
    "cotizacion.capturar", "cotizacion.editar", "cotizacion.comparar",
    "cotizacion.adjudicar", "cotizacion.sobrescribir_seleccion",
    "orden.ver", "orden.crear", "orden.editar", "orden.enviar_aprobacion", "orden.aprobar",
    "orden.enviar", "orden.confirmar", "orden.versionar", "orden.cancelar", "orden.cerrar",
    "recepcion.ver", "recepcion.crear", "recepcion.directa", "recepcion.completar",
    "recepcion.parcial", "recepcion.tolerancia", "recepcion.peso_manual",
    "recepcion.rechazar", "recepcion.reversar", "calidad.inspeccionar", "calidad.liberar",
    "recepcion.cuarentena", "recepcion.devolucion",
    "factura.ver", "factura.capturar", "factura.editar", "factura.conciliar",
    "factura.liberar_diferencia", "factura.bloquear", "factura.cancelar",
)

_LOGISTICA = (
    "embarque.ver", "embarque.crear", "contenedor.gestionar", "contenedor.adjuntar",
    "contenedor.mover", "contenedor.sellar", "embarque.despachar", "embarque.forzar",
    "contenedor.liberar", "etiqueta.imprimir", "contenedor.escanear", "embarque.recibir",
)

_ALMACEN_COMPRAS = (
    "ver", "ver.sucursal_propia", "orden.ver", "directa.ver",
    "recepcion.ver", "recepcion.crear", "recepcion.completar", "recepcion.parcial",
    "recepcion.rechazar", "recepcion.peso_manual",
)

_ALMACEN_LOGISTICA = (
    "embarque.ver", "embarque.recibir", "contenedor.escanear", "contenedor.mover",
    "contenedor.liberar", "etiqueta.imprimir",
)

_ASIGNACIONES: dict[str, dict[str, tuple[str, ...]]] = {
    "system_owner": {"COMPRAS": _COMPRAS, "LOGISTICA": _LOGISTICA},
    "admin": {"COMPRAS": _COMPRAS, "LOGISTICA": _LOGISTICA},
    "gerente": {"COMPRAS": _COMPRAS, "LOGISTICA": _LOGISTICA},
    "almacen": {"COMPRAS": _ALMACEN_COMPRAS, "LOGISTICA": _ALMACEN_LOGISTICA},
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
        logger.info("283: sin tablas de roles/permisos; nada que sembrar.")
        return
    concedidos, omitidos = 0, []
    for rol, modulos in _ASIGNACIONES.items():
        rol_id = _rol_id(conn, rol)
        if rol_id is None:
            omitidos.append(rol)
            continue
        for modulo, acciones in modulos.items():
            for accion in acciones:
                cur = conn.execute(
                    "INSERT OR IGNORE INTO rol_permisos (id, rol_id, modulo, accion, permitido)"
                    " VALUES (?,?,?,?,1)", (new_uuid(), rol_id, modulo, accion))
                concedidos += cur.rowcount if cur.rowcount and cur.rowcount > 0 else 0
    conn.commit()
    logger.info("283: %s permisos de Compras/Logística concedidos; roles ausentes: %s",
                concedidos, omitidos or "ninguno")


up = run
