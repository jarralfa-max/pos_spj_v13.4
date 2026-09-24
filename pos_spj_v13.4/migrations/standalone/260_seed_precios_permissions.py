"""260 — siembra las acciones de `PRECIOS` en `rol_permisos`.

POR QUÉ HACE FALTA
------------------
La migración del vocabulario de Precios a `PRECIOS.<accion>` hizo sus permisos
OTORGABLES desde Configuración → Seguridad → Permisos, pero no se los otorgó a
nadie: `rol_permisos` tenía CERO filas de `PRECIOS` (medido en la base viva).
El efecto real era que sólo el rol `admin` podía operar el módulo, porque
`PermissionQueryService` le devuelve el comodín `{"*"}` por nombre de rol, sin
mirar la base.

`system_owner` —el dueño de la instalación— NO recibe ese comodín:
`ADMIN_ROLE_NAMES` (permission_query_service) contiene admin/superadmin/
administrador, mientras que `_ADMIN_ROLES` (bootstrap/application_context, que
alimenta `is_admin()`) SÍ incluye system_owner. Son dos listas distintas para la
misma pregunta, y esa divergencia es previa a esta migración. La consecuencia
concreta: sin esta siembra, el dueño de la instalación no puede autorizar un
precio bajo mínimo, mientras que `admin` sí.

POR QUÉ ESTO SE REPETIRÁ (deuda declarada, no resuelta aquí)
------------------------------------------------------------
La migración 206 siembra `system_owner` con un producto cartesiano
`_MODULOS × _ACCIONES` congelado en el código. Como `INSERT OR IGNORE` ya corrió
y esa lista no se deriva del catálogo, TODO módulo nacido después queda fuera en
silencio. `PRECIOS` es el primer caso; el próximo contexto acotado tendrá el
mismo problema. Derivar el sembrado de `CANONICAL_MODULE_PERMISSIONS` es la
solución de raíz y se descartó deliberadamente en esta vuelta: aplicarla de
forma retroactiva a instalaciones existentes es una decisión de escalamiento de
privilegios por derecho propio.

ALCANCE DELIBERADO
------------------
Sólo tres roles, los aprobados: `system_owner` y `admin` reciben TODO;
`gerente` recibe el juego operativo, INCLUIDO `precio.minimo.excepcion`, que es
lo único que hace alcanzable la autorización en caliente (la valida otra persona
sobre el terminal de quien vende). `cajero`, `solo_lectura` y el resto **no
reciben nada**: quien vende no fija precios, y conceder por si acaso es lo
contrario de fallar cerrado.

Un rol que no exista se OMITE, nunca se crea: inventar roles desde una migración
de permisos daría acceso a una identidad que nadie definió.
"""

from __future__ import annotations

import logging

from backend.shared.ids import new_uuid

logger = logging.getLogger("spj.migrations.260")

MODULO = "PRECIOS"

#: Las 23 acciones que declara `backend/application/pricing/permissions.py`.
#: Se transcriben en vez de importarse a propósito: una migración es una foto
#: fija: si mañana el contexto añade una acción, esta migración debe seguir
#: sembrando exactamente lo que sembró el día que corrió. El test que la
#: acompaña compara esta lista contra `ALL_PRICING_PERMISSIONS`, así que una
#: errata o una divergencia se ven de inmediato.
_TODAS = (
    "acceder", "ver", "costo.ver", "margen.ver", "auditoria.ver", "exportar",
    "precio.crear", "precio.editar", "precio.minimo.excepcion",
    "volumen.gestionar", "sucursal.gestionar",
    "lista.ver", "lista.crear", "lista.editar", "lista.enviar",
    "lista.aprobar", "lista.activar", "lista.desactivar",
    "lista.cliente.asignar",
    "costo.gestionar", "costo.estandar.fijar",
    "configuracion.ver", "configuracion.gestionar",
)

#: Operativo. Queda fuera la gestión de COSTOS (`costo.gestionar`,
#: `costo.estandar.fijar`) —el costo lo fija Finanzas/Compras, no quien vende— y
#: la configuración del módulo. Sí entra `lista.aprobar` junto con
#: `lista.crear`: la segregación de funciones compara IDENTIDADES, así que un
#: gerente sigue sin poder aprobar SU PROPIA lista, pero otro gerente sí.
_GERENTE = tuple(a for a in _TODAS if a not in {
    "costo.gestionar", "costo.estandar.fijar",
    "configuracion.ver", "configuracion.gestionar",
})

_ASIGNACIONES: dict[str, tuple[str, ...]] = {
    "system_owner": _TODAS,
    "admin": _TODAS,
    "gerente": _GERENTE,
}


def _tabla_existe(conn, nombre: str) -> bool:
    return conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (nombre,)
    ).fetchone() is not None


def _rol_id(conn, nombre: str) -> str | None:
    """Mismo criterio de búsqueda que `SqlitePermissionRepository.
    role_id_for_name`: sin él, un rol guardado como 'Gerente' no se encontraría
    y la siembra fallaría en silencio justo en la instalación que la necesita."""
    fila = conn.execute(
        "SELECT id FROM roles WHERE lower(trim(nombre))=?", (nombre.strip().lower(),)
    ).fetchone()
    return None if fila is None else str(fila[0])


def run(conn) -> None:
    if not (_tabla_existe(conn, "roles") and _tabla_existe(conn, "rol_permisos")):
        logger.info("260: sin tablas de roles/permisos; nada que sembrar.")
        return

    concedidos, omitidos = 0, []
    for rol, acciones in _ASIGNACIONES.items():
        rol_id = _rol_id(conn, rol)
        if rol_id is None:
            omitidos.append(rol)
            continue
        for accion in acciones:
            # Idempotente de verdad: `rol_permisos` declara
            # UNIQUE(rol_id, modulo, accion) — verificado en la base viva.
            cur = conn.execute(
                "INSERT OR IGNORE INTO rol_permisos (id, rol_id, modulo, accion, permitido) "
                "VALUES (?,?,?,?,1)",
                (new_uuid(), rol_id, MODULO, accion),
            )
            concedidos += cur.rowcount if cur.rowcount and cur.rowcount > 0 else 0
    conn.commit()
    logger.info("260: %s permisos PRECIOS concedidos; roles ausentes omitidos: %s",
                concedidos, omitidos or "ninguno")


up = run
