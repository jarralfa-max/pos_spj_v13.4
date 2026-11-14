"""359 — permisos de Caja que se verifican y asignaciones de turno (SDLC-ARQ-SHIFT-003).

Hasta hoy `CAJA.turno.forzar_cierre` servía para TODO lo ajeno: suspender,
reanudar, pre-cerrar y mover efectivo en el turno de otro cajero; y
`CAJA.turno.cerrar` no se comprobaba en ningún lado. Ahora intervenir un turno
(`turno.intervenir`), mover efectivo ajeno (`movimiento.intervenir`) y forzar el
cierre son permisos distintos, y generar el Corte Z final también exige
`turno.cerrar`.

Nadie pierde lo que ya podía hacer:

* quien tenía `turno.forzar_cierre` recibe `turno.intervenir` y
  `movimiento.intervenir`;
* quien tenía `corte_z.generar` recibe `turno.cerrar`.

Sólo agrega filas. `cash_shift_assignments` nunca se había escrito: cada turno
vivo recibe la asignación activa de su cajero. Idempotente.
"""

from __future__ import annotations

import logging

from backend.shared.ids import new_uuid

logger = logging.getLogger("spj.migrations.359")

#: acción que ya tenía el rol → acciones que la conservan.
_DERIVADAS = {
    "turno.forzar_cierre": ("turno.intervenir", "movimiento.intervenir"),
    "corte_z.generar": ("turno.cerrar",),
}
#: Foto fija de `CashShiftLifecyclePolicy.ACTIVE_STATUSES`.
_ESTADOS_ACTIVOS = ("OPENING", "OPEN", "SUSPENDED", "PENDING_COUNT", "COUNTING", "COUNTED",
                    "PENDING_REVIEW", "CLOSING")


def _tabla_existe(conn, nombre: str) -> bool:
    return conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (nombre,)
    ).fetchone() is not None


def _sembrar_permisos(conn) -> int:
    concedidos = 0
    for origen, derivadas in _DERIVADAS.items():
        roles = [str(fila[0]) for fila in conn.execute(
            "SELECT DISTINCT rol_id FROM rol_permisos"
            " WHERE upper(modulo)='CAJA' AND lower(accion)=? AND permitido=1", (origen,))]
        for rol_id in roles:
            for accion in derivadas:
                if conn.execute(
                        "SELECT 1 FROM rol_permisos WHERE rol_id=? AND upper(modulo)='CAJA'"
                        " AND lower(accion)=?", (rol_id, accion)).fetchone():
                    continue
                conn.execute(
                    "INSERT INTO rol_permisos (id, rol_id, modulo, accion, permitido)"
                    " VALUES (?,?,?,?,1)", (new_uuid(), rol_id, "CAJA", accion))
                concedidos += 1
    return concedidos


def _asignar_turnos_vivos(conn) -> int:
    marcas = ",".join("?" for _ in _ESTADOS_ACTIVOS)
    turnos = conn.execute(
        "SELECT id,branch_id,register_id,drawer_id,terminal_id,cashier_user_id,opened_at"
        f" FROM cash_shifts s WHERE status IN ({marcas}) AND NOT EXISTS ("
        "   SELECT 1 FROM cash_shift_assignments a"
        "   WHERE a.shift_id=s.id AND a.status='ACTIVE')", _ESTADOS_ACTIVOS).fetchall()
    for turno in turnos:
        conn.execute(
            """INSERT INTO cash_shift_assignments
            (id,shift_id,branch_id,register_id,drawer_id,terminal_id,cashier_user_id,
             assigned_by,status,assigned_at)
            VALUES (?,?,?,?,?,?,?,?,'ACTIVE',?)""",
            (new_uuid(), turno[0], turno[1], turno[2], turno[3], turno[4], turno[5], turno[5],
             turno[6]))
    return len(turnos)


def run(conn) -> None:
    concedidos = asignados = 0
    if _tabla_existe(conn, "rol_permisos"):
        concedidos = _sembrar_permisos(conn)
    if _tabla_existe(conn, "cash_shifts") and _tabla_existe(conn, "cash_shift_assignments"):
        asignados = _asignar_turnos_vivos(conn)
    conn.commit()
    logger.info("359: %s permisos conservados, %s turnos vivos asignados", concedidos, asignados)


up = run
