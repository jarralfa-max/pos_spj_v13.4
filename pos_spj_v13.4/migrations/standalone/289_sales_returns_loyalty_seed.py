"""289 — Devoluciones con reembolso, canje y puntos por compra (2026-10-02).

Siembra lo que el usuario decidió para que lo construido funcione desde el
primer día. Idempotente: no pisa nada que ya exista.

1. Permisos (`rol_permisos`):
   * `GROWTH_ENGINE.puntos.canjear` → cajero, gerente, admin, system_owner
     (canje de puntos en el POS).
   * `CAJA.reembolso.ver/solicitar/autorizar` → gerente, admin, system_owner
     (reembolso de devoluciones; quien autoriza siempre es OTRA persona).
   * `GROWTH_ENGINE.ver` y `GROWTH_ENGINE.configuracion.ver/editar` → admin,
     system_owner (Fidelidad → Configuración: reglas de acumulación, canje y
     caducidad).
   Un rol que no exista se OMITE, nunca se crea.
2. Tope de reembolso en efectivo por operación: $5,000 (`cash_operation_limits`,
   tipo REFUND, alcance SYSTEM). Sin tope Caja rechazaba todo reembolso. Sólo
   se siembra si no hay ningún tope REFUND, y sólo si existe un usuario
   system_owner que figure como quien lo creó (la columna exige UUIDv7 real).
3. Reglas de puntos (`configuraciones`): 1 punto por cada $10, el crédito
   acumula, vigencia de 12 meses. Editables en Fidelidad → Ajustes.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from backend.shared.ids import new_uuid

logger = logging.getLogger("spj.migrations.289")

_PERMISOS: dict[str, dict[str, tuple[str, ...]]] = {
    "cajero": {"GROWTH_ENGINE": ("puntos.canjear",)},
    "gerente": {"GROWTH_ENGINE": ("puntos.canjear",),
                "CAJA": ("reembolso.ver", "reembolso.solicitar", "reembolso.autorizar")},
    "admin": {"GROWTH_ENGINE": ("puntos.canjear", "ver", "configuracion.ver", "configuracion.editar"),
              "CAJA": ("reembolso.ver", "reembolso.solicitar", "reembolso.autorizar")},
    "system_owner": {"GROWTH_ENGINE": ("puntos.canjear", "ver", "configuracion.ver", "configuracion.editar"),
                     "CAJA": ("reembolso.ver", "reembolso.solicitar", "reembolso.autorizar")},
}

_REGLAS_PUNTOS = (
    ("loyalty_pesos_por_punto", "10", "Pesos de compra por cada punto"),
    ("loyalty_credito_acumula", "1", "Las ventas a crédito acumulan puntos"),
    ("loyalty_meses_caducidad", "12", "Meses de vigencia de los puntos (0 = no caducan)"),
)

REFUND_CAP = "5000"


def _tabla(conn, nombre: str) -> bool:
    return conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
                        (nombre,)).fetchone() is not None


def _sembrar_permisos(conn) -> int:
    if not (_tabla(conn, "roles") and _tabla(conn, "rol_permisos")):
        return 0
    concedidos = 0
    for rol, modulos in _PERMISOS.items():
        fila = conn.execute("SELECT id FROM roles WHERE lower(trim(nombre))=?",
                            (rol,)).fetchone()
        if fila is None:
            continue
        for modulo, acciones in modulos.items():
            for accion in acciones:
                cur = conn.execute(
                    "INSERT OR IGNORE INTO rol_permisos (id, rol_id, modulo, accion, permitido)"
                    " VALUES (?,?,?,?,1)", (new_uuid(), str(fila[0]), modulo, accion))
                concedidos += max(cur.rowcount or 0, 0)
    return concedidos


def _sembrar_tope(conn) -> bool:
    if not _tabla(conn, "cash_operation_limits"):
        return False
    if conn.execute("SELECT 1 FROM cash_operation_limits WHERE operation_type='REFUND'"
                    ).fetchone():
        return False
    creador = None
    if _tabla(conn, "usuarios"):
        fila = conn.execute(
            "SELECT id FROM usuarios WHERE lower(trim(rol))='system_owner' ORDER BY id LIMIT 1"
        ).fetchone()
        creador = str(fila[0]) if fila else None
    if not creador or len(creador) != 36 or creador[14] != "7":
        return False
    conn.execute(
        "INSERT INTO cash_operation_limits (id, operation_type, approval_threshold, hard_cap,"
        " scope_type, scope_id, effective_from, effective_to, created_by)"
        " VALUES (?, 'REFUND', ?, ?, 'SYSTEM', NULL, ?, NULL, ?)",
        (new_uuid(), REFUND_CAP, REFUND_CAP,
         datetime.now(timezone.utc).isoformat(timespec="seconds"), creador))
    return True


def _sembrar_reglas(conn) -> int:
    if not _tabla(conn, "configuraciones"):
        return 0
    sembradas = 0
    for clave, valor, descripcion in _REGLAS_PUNTOS:
        cur = conn.execute(
            "INSERT OR IGNORE INTO configuraciones (clave, valor, grupo, descripcion)"
            " VALUES (?,?, 'fidelidad', ?)", (clave, valor, descripcion))
        sembradas += max(cur.rowcount or 0, 0)
    return sembradas


def run(conn) -> None:
    permisos = _sembrar_permisos(conn)
    tope = _sembrar_tope(conn)
    reglas = _sembrar_reglas(conn)
    conn.commit()
    logger.info("289: %s permisos, tope de reembolso %s, %s reglas de puntos.",
                permisos, "sembrado" if tope else "sin cambio", reglas)


up = run
