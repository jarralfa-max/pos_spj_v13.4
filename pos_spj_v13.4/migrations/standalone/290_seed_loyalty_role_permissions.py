"""290 — siembra las acciones de Fidelidad y Tarjetas en `rol_permisos`.

POR QUÉ HACE FALTA (medido en la base viva el 2026-10-02)
---------------------------------------------------------
Fidelidad (`GROWTH_ENGINE`) y Tarjetas (`TARJETAS_FIDELIDAD`) declaran 58 + 27
acciones granulares, todas OTORGABLES desde la matriz de permisos, pero el
dueño de la instalación (`system_owner`) sólo tenía las 4 que sembró la 289
(`ver`, `configuracion.ver/editar`, `puntos.canjear`) y CERO de Tarjetas.

El efecto en pantalla: el dueño veía el módulo, pero crear un programa, inscribir
a un cliente, emitir un cupón o una tarjeta fallaba con "permiso denegado". Es el
mismo mecanismo que la 260 documentó para Precios: la 206 siembra `system_owner`
con una lista congelada de módulos, y `admin` se salva sólo porque
`PermissionQueryService` le da el comodín `*` por nombre de rol.

ALCANCE (mismo criterio que la 260, aprobado entonces por el usuario)
--------------------------------------------------------------------
* `system_owner` y `admin`: TODO.
* `gerente`: el juego OPERATIVO — atender miembros, mover puntos, emitir y
  canjear instrumentos, emitir/asignar/bloquear/reponer tarjetas, imprimir y
  reimprimir. Queda fuera lo que define el programa o lo aprueba: crear,
  aprobar, activar o suspender programas; gestionar niveles, recompensas y
  retos; aprobar/activar campañas; anular reglas de cupón; recargar/ajustar
  vales; sortear; resolver fraude; configuración; diseñar, aprobar o activar
  plantillas; aprobar lotes y rotar QR. Ajustar puntos SÍ entra: la
  segregación compara IDENTIDADES, así que el ajuste lo aprueba otra persona.
* `cajero`, `almacen`, `repartidor`, `solo_lectura`: nada nuevo. El canje en
  caja ya lo dio la 289, y la acumulación por venta usa la política DELEGADA
  de Ventas, no permisos del cajero.

Un rol que no exista se OMITE, nunca se crea.
"""

from __future__ import annotations

import logging

from backend.shared.ids import new_uuid

logger = logging.getLogger("spj.migrations.290")

#: Foto fija de `backend/application/loyalty/permissions.py` el día que corrió.
#: El test que la acompaña la compara contra `ALL_LOYALTY_PERMISSIONS`.
_FIDELIDAD = (
    "ver", "acceso", "dashboard.ver", "auditoria.ver",
    "programa.ver", "programa.crear", "programa.editar", "programa.aprobar",
    "programa.activar", "programa.suspender",
    "membresia.ver", "membresia.inscribir", "membresia.suspender", "membresia.cerrar",
    "puntos.ver", "puntos.acreditar", "puntos.canjear", "puntos.ajustar",
    "puntos.reversar", "puntos.auditar",
    "nivel.ver", "nivel.gestionar", "recompensa.ver", "recompensa.gestionar",
    "recompensa.canjear", "reto.ver", "reto.gestionar",
    "referido.ver", "referido.gestionar", "referido.aprobar",
    "cumpleanos.ver", "cumpleanos.gestionar", "retencion.ver", "retencion.gestionar",
    "campana.ver", "campana.crear", "campana.aprobar", "campana.activar",
    "cupon.ver", "cupon.emitir", "cupon.canjear", "cupon.cancelar", "cupon.override",
    "vale.ver", "vale.emitir", "vale.canjear", "vale.recargar", "vale.cancelar",
    "vale.ajustar",
    "sorteo.ver", "sorteo.gestionar", "sorteo.sortear", "sorteo.boleto_imprimir",
    "sorteo.boleto_reimprimir",
    "antifraude.ver", "antifraude.gestionar",
    "configuracion.ver", "configuracion.editar",
)

#: Foto fija de `backend/application/loyalty_cards/permissions.py`.
_TARJETAS = (
    "ver", "acceso",
    "tarjeta.ver", "tarjeta.crear", "tarjeta.asignar", "tarjeta.activar",
    "tarjeta.bloquear", "tarjeta.reponer", "tarjeta.cancelar",
    "plantilla.ver", "plantilla.crear", "plantilla.editar", "plantilla.importar",
    "plantilla.aprobar", "plantilla.activar", "plantilla.archivar",
    "disenador.acceso", "formato.gestionar", "pliego.gestionar",
    "lote.crear", "lote.aprobar", "lote.imprimir", "reimprimir",
    "qr.rotar", "auditoria.ver", "configuracion.ver", "configuracion.editar",
)

_FIDELIDAD_NO_GERENTE = frozenset({
    "programa.crear", "programa.editar", "programa.aprobar", "programa.activar",
    "programa.suspender", "nivel.gestionar", "recompensa.gestionar", "reto.gestionar",
    "referido.aprobar", "cumpleanos.gestionar", "retencion.gestionar",
    "campana.aprobar", "campana.activar", "cupon.override", "vale.recargar",
    "vale.ajustar", "sorteo.gestionar", "sorteo.sortear", "antifraude.gestionar",
    "configuracion.editar", "puntos.auditar",
})

_TARJETAS_NO_GERENTE = frozenset({
    "plantilla.crear", "plantilla.editar", "plantilla.importar", "plantilla.aprobar",
    "plantilla.activar", "plantilla.archivar", "disenador.acceso", "formato.gestionar",
    "pliego.gestionar", "lote.aprobar", "qr.rotar", "configuracion.editar",
})

_ASIGNACIONES: dict[str, dict[str, tuple[str, ...]]] = {
    "system_owner": {"GROWTH_ENGINE": _FIDELIDAD, "TARJETAS_FIDELIDAD": _TARJETAS},
    "admin": {"GROWTH_ENGINE": _FIDELIDAD, "TARJETAS_FIDELIDAD": _TARJETAS},
    "gerente": {
        "GROWTH_ENGINE": tuple(a for a in _FIDELIDAD if a not in _FIDELIDAD_NO_GERENTE),
        "TARJETAS_FIDELIDAD": tuple(a for a in _TARJETAS if a not in _TARJETAS_NO_GERENTE),
    },
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
        logger.info("290: sin tablas de roles/permisos; nada que sembrar.")
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
                    "INSERT OR IGNORE INTO rol_permisos (id, rol_id, modulo, accion, permitido) "
                    "VALUES (?,?,?,?,1)",
                    (new_uuid(), rol_id, modulo, accion),
                )
                concedidos += max(cur.rowcount or 0, 0)
    conn.commit()
    logger.info("290: %s permisos de Fidelidad/Tarjetas concedidos; roles omitidos: %s",
                concedidos, omitidos or "ninguno")


up = run
