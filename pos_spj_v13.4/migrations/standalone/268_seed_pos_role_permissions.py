"""268 — siembra los permisos del POS (y de reserva de inventario) por rol.

POR QUÉ HACE FALTA (medido el 2026-09-18 en la base real)
---------------------------------------------------------
Los permisos finos del POS (`POS.venta.linea_agregar`, `POS.venta.completar`,
`POS.pago.efectivo`…) son OTORGABLES desde Configuración → Seguridad → Permisos,
pero nadie los tenía: `rol_permisos` sólo guarda las 5 acciones gruesas del
sembrado base (ver/crear/editar/eliminar/exportar). Resultado, con la sesión
real: **Ana (cajero) y demo (gerente) no podían ni agregar una línea**; sólo
vendían admin y system_owner, por comodín de rol. Mismo patrón que la 260 cerró
para Precios ("otorgable ≠ otorgado").

Además, desde la Fase 6 el cobro reserva y descuenta inventario con el permiso
de QUIEN COBRA (`INVENTARIO.reserva.crear/liberar`): sin ellos ningún cajero
podría cerrar una venta.

REPARTO — decisión del usuario: "cajero vende, gerente autoriza"
---------------------------------------------------------------
- cajero: vender (líneas, cobrar, suspender/reanudar), descuento dentro del
  umbral, pagos de contado (efectivo, tarjeta, transferencia, mixto, Mercado
  Pago), reimprimir ticket, báscula y reservar/liberar inventario.
- gerente: todo lo anterior + cancelar, devolución, reverso, crédito, factura,
  cajón manual, descuento grande/personalizado, precio y las autorizaciones en
  caliente (bajo el mínimo, vender sin existencia).
- admin y system_owner: todo.

Un rol que no exista se OMITE, nunca se crea. `INSERT OR IGNORE`: no pisa lo que
un administrador ya haya otorgado o revocado.
"""

from __future__ import annotations

import logging

from backend.shared.ids import new_uuid

logger = logging.getLogger("spj.migrations.268")

#: Todo el vocabulario de `backend/application/sales/permissions.py`, sin el
#: prefijo `POS.`. Transcrito, no importado: la migración es una foto fija. El
#: test que la acompaña lo compara contra `ALL_SALES_PERMISSIONS`.
_POS_TODAS = (
    "ver", "acceso", "abrir", "crear",
    "venta.linea_agregar", "venta.linea_actualizar", "venta.linea_eliminar",
    "venta.completar", "cancelar", "venta.suspender", "venta.reanudar",
    "venta.sin_existencia",
    "descuento", "descuento.personalizado", "descuento.sobrescribir",
    "precio.sobrescribir",
    "pago.efectivo", "pago.tarjeta", "pago.transferencia", "pago.mixto",
    "pago.credito", "pago.mercado_pago",
    "devolucion", "reverso", "ticket.reimprimir", "factura.solicitar",
    "cajon.abrir_manual", "bascula.usar", "dispositivo.diagnostico_ver",
)

_POS_CAJERO = (
    "ver", "acceso", "abrir", "crear",
    "venta.linea_agregar", "venta.linea_actualizar", "venta.linea_eliminar",
    "venta.completar", "venta.suspender", "venta.reanudar",
    "descuento",
    "pago.efectivo", "pago.tarjeta", "pago.transferencia", "pago.mixto",
    "pago.mercado_pago",
    "ticket.reimprimir", "bascula.usar",
)

#: Lo que el cobro pide a Inventario con el permiso de quien cobra.
_INVENTARIO_VENTA = ("reserva.ver", "reserva.crear", "reserva.liberar")

_ASIGNACIONES: dict[str, dict[str, tuple[str, ...]]] = {
    "system_owner": {"POS": _POS_TODAS, "INVENTARIO": _INVENTARIO_VENTA},
    "admin": {"POS": _POS_TODAS, "INVENTARIO": _INVENTARIO_VENTA},
    "gerente": {"POS": _POS_TODAS, "INVENTARIO": _INVENTARIO_VENTA},
    "cajero": {"POS": _POS_CAJERO, "INVENTARIO": _INVENTARIO_VENTA},
}


def _tabla_existe(conn, nombre: str) -> bool:
    return conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (nombre,)
    ).fetchone() is not None


def _rol_id(conn, nombre: str) -> str | None:
    """Mismo criterio que `SqlitePermissionRepository.role_id_for_name`."""
    fila = conn.execute(
        "SELECT id FROM roles WHERE lower(trim(nombre))=?", (nombre.strip().lower(),)
    ).fetchone()
    return None if fila is None else str(fila[0])


def run(conn) -> None:
    if not (_tabla_existe(conn, "roles") and _tabla_existe(conn, "rol_permisos")):
        logger.info("268: sin tablas de roles/permisos; nada que sembrar.")
        return

    concedidos, omitidos = 0, []
    for rol, por_modulo in _ASIGNACIONES.items():
        rol_id = _rol_id(conn, rol)
        if rol_id is None:
            omitidos.append(rol)
            continue
        for modulo, acciones in por_modulo.items():
            for accion in acciones:
                cur = conn.execute(
                    "INSERT OR IGNORE INTO rol_permisos (id, rol_id, modulo, accion, permitido) "
                    "VALUES (?,?,?,?,1)", (new_uuid(), rol_id, modulo, accion))
                concedidos += cur.rowcount if cur.rowcount and cur.rowcount > 0 else 0
    conn.commit()
    logger.info("268: %s permisos de POS/reserva concedidos; roles ausentes: %s",
                concedidos, omitidos or "ninguno")


up = run
