"""306 — siembra las acciones granulares de Caja en `rol_permisos`.

POR QUÉ HACE FALTA (medido en una copia de la base viva el 2026-10-07)
-------------------------------------------------------------------
Caja declara 93 acciones (`backend/application/cash_register/permissions.py`),
todas OTORGABLES desde la matriz de permisos, pero NINGÚN rol tenía una sola:
los roles conservaban los códigos gruesos de la Caja vieja (`ver`, `crear`,
`editar`, `eliminar`, `exportar`, `reembolso.*`). El dueño y el administrador
operaban porque el evaluador de sesión les da paso libre por rol; cualquier
otro usuario quedaba fuera. Efecto: un cajero no podía abrir turno, y como el
POS exige turno abierto para cobrar (decisión del 2026-09-18), un cajero no
podía VENDER.

La matriz de roles de Caja sólo existía dentro de un test
(`tests/unit/cash_register/test_cash_register_role_matrix.py`), con nombres de
rol que no existen en ninguna base (`supervisor_caja`, `receptor_valores`...).

ALCANCE (decisión del usuario, 2026-10-07)
-----------------------------------------
* `system_owner` y `admin`: TODO.
* `gerente`: supervisión de su sucursal — todo lo del cajero más revisar y
  resolver diferencias, autorizar excesos y reembolsos, reversar, forzar
  cierre, ver el esperado, recibir/disputar entregas, depósitos, reimprimir,
  diagnosticar hardware y consultar configuración. Fuera: lo que define la
  instalación (alta/edición/bloqueo de cajas, cajones y terminales, hardware,
  medios de pago, configuración, WhatsApp, sincronización) y el castigo de
  diferencias.
* `cajero`: opera SU turno completo — abrir, suspender, reanudar, cerrar;
  ingresos/retiros dentro de límite; retiro a bóveda; conteo ciego; Corte X y
  Corte Z; explicar su diferencia; preparar y entregar valores; ejecutar
  reembolsos ya autorizados por Ventas dentro de límite; abrir cajón con venta;
  operar terminal; imprimir. NO revisa ni resuelve diferencias, no reversa, no
  configura y no ve el esperado antes de contar.
* `solo_lectura`: consulta sin importes sensibles.
* `almacen`, `repartidor`: nada.

Además borra `crear`/`editar`/`eliminar` de CAJA: no existen en el catálogo
(nadie los comprueba) y la matriz de permisos no puede mostrarlos (§58.8).

Un rol que no exista se OMITE, nunca se crea.
"""

from __future__ import annotations

import logging

from backend.shared.ids import new_uuid

logger = logging.getLogger("spj.migrations.306")

#: Foto fija de `CashPermissions` el día que corrió (sin el prefijo `CAJA.`).
#: El test que la acompaña la compara contra `ALL_CASH_PERMISSIONS`.
_TODAS = (
    "ver", "ver.sucursal_propia", "ver.sucursales_asignadas", "ver.todas_sucursales",
    "ver.importes_sensibles", "ver.auditoria", "exportar",
    "caja.ver", "caja.crear", "caja.editar", "caja.activar", "caja.bloquear", "caja.retirar",
    "cajon.ver", "cajon.gestionar", "cajon.abrir", "cajon.abrir_sin_venta",
    "terminal.ver", "terminal.gestionar", "terminal.operar",
    "turno.ver", "turno.abrir", "turno.suspender", "turno.reanudar", "turno.pre_cerrar",
    "turno.cerrar", "turno.forzar_cierre", "turno.reasignar",
    "movimiento.ver", "movimiento.ingreso", "movimiento.retiro", "movimiento.safe_drop",
    "movimiento.reversar", "movimiento.autorizar_exceso",
    "conteo.ver", "conteo.iniciar", "conteo.capturar", "conteo.confirmar",
    "conteo.ver_esperado", "conteo.cancelar", "conteo.sobrescribir",
    "corte_x.ver", "corte_x.generar", "corte_x.imprimir", "corte_x.reimprimir",
    "corte_z.ver", "corte_z.generar", "corte_z.revisar", "corte_z.imprimir",
    "corte_z.reimprimir",
    "diferencia.ver", "diferencia.explicar", "diferencia.revisar", "diferencia.resolver",
    "diferencia.castigar",
    "retiro_seguridad.ver", "retiro_seguridad.crear", "retiro_seguridad.autorizar",
    "entrega.ver", "entrega.preparar", "entrega.entregar", "entrega.recibir",
    "entrega.disputar", "entrega.cancelar",
    "deposito.ver", "deposito.preparar", "deposito.cancelar",
    "pago.ver", "pago.registrar", "pago.reversar",
    "medio_pago.ver", "medio_pago.gestionar",
    "terminal_pago.ver", "terminal_pago.gestionar", "terminal_pago.conciliar_operacion",
    "reembolso.ver", "reembolso.solicitar", "reembolso.ejecutar", "reembolso.autorizar",
    "reembolso.sobrescribir",
    "evento_cajon.ver",
    "hardware.ver", "hardware.diagnosticar", "hardware.gestionar",
    "imprimir", "reimprimir",
    "configuracion.ver", "configuracion.editar",
    "notificacion.ver", "notificacion.gestionar", "whatsapp.gestionar",
    "sync.ver", "sync.gestionar",
)

_CAJERO = (
    "ver", "ver.sucursal_propia",
    "turno.ver", "turno.abrir", "turno.suspender", "turno.reanudar", "turno.pre_cerrar",
    "turno.cerrar",
    "movimiento.ver", "movimiento.ingreso", "movimiento.retiro", "movimiento.safe_drop",
    "retiro_seguridad.ver", "retiro_seguridad.crear",
    "conteo.ver", "conteo.iniciar", "conteo.capturar", "conteo.confirmar",
    "corte_x.ver", "corte_x.generar", "corte_x.imprimir",
    "corte_z.ver", "corte_z.generar", "corte_z.imprimir",
    "diferencia.ver", "diferencia.explicar",
    "entrega.ver", "entrega.preparar", "entrega.entregar",
    "pago.ver", "pago.registrar",
    "reembolso.ver", "reembolso.solicitar", "reembolso.ejecutar",
    "cajon.abrir", "terminal.operar", "evento_cajon.ver",
    "imprimir",
)

_GERENTE_EXTRA = (
    "ver.sucursales_asignadas", "ver.importes_sensibles", "ver.auditoria", "exportar",
    "caja.ver", "cajon.ver", "terminal.ver",
    "turno.forzar_cierre", "turno.reasignar",
    "movimiento.reversar", "movimiento.autorizar_exceso",
    "conteo.ver_esperado", "conteo.cancelar", "conteo.sobrescribir",
    "corte_x.reimprimir", "corte_z.revisar", "corte_z.reimprimir",
    "diferencia.revisar", "diferencia.resolver",
    "retiro_seguridad.autorizar",
    "entrega.recibir", "entrega.disputar", "entrega.cancelar",
    "deposito.ver", "deposito.preparar", "deposito.cancelar",
    "pago.reversar",
    "medio_pago.ver", "terminal_pago.ver", "terminal_pago.conciliar_operacion",
    "reembolso.autorizar", "reembolso.sobrescribir",
    "cajon.abrir_sin_venta",
    "hardware.ver", "hardware.diagnosticar",
    "reimprimir",
    "configuracion.ver", "notificacion.ver", "sync.ver",
)

_SOLO_LECTURA = (
    "ver", "ver.sucursal_propia",
    "turno.ver", "movimiento.ver", "conteo.ver", "corte_x.ver", "corte_z.ver",
    "diferencia.ver", "entrega.ver", "deposito.ver", "reembolso.ver", "evento_cajon.ver",
)

_ASIGNACIONES: dict[str, tuple[str, ...]] = {
    "system_owner": _TODAS,
    "admin": _TODAS,
    "gerente": _CAJERO + _GERENTE_EXTRA,
    "cajero": _CAJERO,
    "solo_lectura": _SOLO_LECTURA,
}

#: Códigos gruesos de la Caja vieja: no están en el catálogo y nadie los comprueba.
_LEGACY = ("crear", "editar", "eliminar")


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
        logger.info("306: sin tablas de roles/permisos; nada que sembrar.")
        return
    borrados = conn.execute(
        "DELETE FROM rol_permisos WHERE upper(modulo)='CAJA' AND lower(accion) IN (?,?,?)",
        _LEGACY,
    ).rowcount or 0
    concedidos, omitidos = 0, []
    for rol, acciones in _ASIGNACIONES.items():
        rol_id = _rol_id(conn, rol)
        if rol_id is None:
            omitidos.append(rol)
            continue
        ya = {
            str(fila[0]).lower()
            for fila in conn.execute(
                "SELECT accion FROM rol_permisos WHERE rol_id=? AND upper(modulo)='CAJA'",
                (rol_id,),
            )
        }
        for accion in dict.fromkeys(acciones):
            if accion in ya:
                continue
            conn.execute(
                "INSERT INTO rol_permisos (id, rol_id, modulo, accion, permitido) "
                "VALUES (?,?,?,?,1)",
                (new_uuid(), rol_id, "CAJA", accion),
            )
            concedidos += 1
    conn.commit()
    logger.info("306: %s permisos de Caja concedidos, %s gruesos borrados; roles omitidos: %s",
                concedidos, borrados, omitidos or "ninguno")


up = run
