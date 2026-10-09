"""307 — catálogos mínimos de Caja: denominaciones, motivos, límites y tolerancia.

POR QUÉ HACE FALTA (medido en una copia de la base viva el 2026-10-07)
-------------------------------------------------------------------
Las cuatro tablas nacían vacías y Caja falla cerrado sin ellas, así que un turno
no podía completarse nunca:

* `cash_denominations` vacía → el conteo ciego no tenía qué contar y no podía
  confirmarse → sin conteo confirmado no hay Corte Z → el turno jamás cerraba
  (el turno real llevaba abierto desde el 2026-09-25).
* `cash_operation_limits` sin OPENING_FLOAT / MANUAL_MOVEMENT / SAFE_DROP → el
  tope vale 0 y Caja rechazaba todo fondo, ingreso, retiro y retiro a bóveda.
* `cash_movement_reasons` vacía y SIN escritor → el retiro a bóveda era
  imposible.
* `cash_difference_policies` vacía y SIN escritor → cualquier faltante o
  sobrante impedía generar el Corte Z.

VALORES (decisión del usuario, 2026-10-07)
-----------------------------------------
* Límites «moderados»: fondo inicial sin autorización hasta $2,000, tope $5,000;
  ingreso/retiro manual autorización arriba de $1,000, tope $5,000; retiro a
  bóveda autorización arriba de $10,000, tope $50,000.
* Tolerancia: hasta $10 la diferencia queda registrada dentro de tolerancia; de
  $10 a $200 pide revisión; más de $200 es crítica. Reincidencia: 3 en 30 días.
* Denominaciones MXN en circulación (Banxico). El $20 existe como billete y como
  moneda con el mismo valor: el conteo es por VALOR, así que es una sola fila.
* Motivos: los de §14 (movimientos manuales) y §15 (retiros de seguridad).

Todo queda editable en Caja → Configuración. Cada catálogo se siembra SÓLO si
no tiene ya una fila vigente (la instalación pudo capturarlo antes).
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone

from backend.shared.ids import new_uuid

logger = logging.getLogger("spj.migrations.307")

_DESDE = "2026-01-01T00:00:00+00:00"

_DENOMINACIONES = (
    ("1000", "Billete $1,000"), ("500", "Billete $500"), ("200", "Billete $200"),
    ("100", "Billete $100"), ("50", "Billete $50"), ("20", "$20 (billete o moneda)"),
    ("10", "Moneda $10"), ("5", "Moneda $5"), ("2", "Moneda $2"), ("1", "Moneda $1"),
    ("0.50", "Moneda $0.50"),
)

#: (código, nombre, tipo de movimiento, requiere autorización)
_MOTIVOS = (
    ("CHANGE_ADDITION", "Dotación de cambio", "MANUAL_INCOME", 0),
    ("CASH_CORRECTION_IN", "Corrección autorizada (entrada)", "MANUAL_INCOME", 1),
    ("OTHER_INCOME_AUTHORIZED", "Otro ingreso autorizado", "MANUAL_INCOME", 1),
    ("AUTHORIZED_OPERATION", "Operación de caja autorizada", "MANUAL_WITHDRAWAL", 0),
    ("CASH_CORRECTION_OUT", "Corrección autorizada (salida)", "MANUAL_WITHDRAWAL", 1),
    ("OTHER_WITHDRAWAL_AUTHORIZED", "Otra salida autorizada", "MANUAL_WITHDRAWAL", 1),
    ("CASH_LIMIT", "Exceso de efectivo en cajón", "SAFE_DROP", 0),
    ("SCHEDULED", "Retiro programado", "SAFE_DROP", 0),
    ("SECURITY_REQUEST", "Solicitud de seguridad", "SAFE_DROP", 0),
    ("MANUAL_AUTHORIZED", "Retiro manual autorizado", "SAFE_DROP", 1),
    ("PARTIAL_CLOSE", "Cierre parcial", "SAFE_DROP", 0),
)

#: (operación, autorización arriba de, tope)
_LIMITES = (
    ("OPENING_FLOAT", "2000", "5000"),
    ("MANUAL_MOVEMENT", "1000", "5000"),
    ("SAFE_DROP", "10000", "50000"),
)

_TOLERANCIA = ("10", "200", 30, 3, ("IN_APP", "WHATSAPP"))


def _tabla(conn, nombre: str) -> bool:
    return conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (nombre,)
    ).fetchone() is not None


def _vigente(conn, sql: str, params: tuple = ()) -> bool:
    ahora = datetime.now(timezone.utc).isoformat(timespec="seconds")
    return conn.execute(sql, params + (ahora, ahora)).fetchone() is not None


def _creador(conn) -> str | None:
    if not _tabla(conn, "usuarios"):
        return None
    fila = conn.execute(
        "SELECT id FROM usuarios WHERE lower(trim(rol))='system_owner' ORDER BY id LIMIT 1"
    ).fetchone()
    creador = str(fila[0]) if fila else None
    return creador if creador and len(creador) == 36 and creador[14] == "7" else None


def run(conn) -> None:
    sembrado: dict[str, int] = {}
    if _tabla(conn, "cash_denominations") and not _vigente(
            conn, "SELECT 1 FROM cash_denominations WHERE currency_code='MXN' AND active=1 "
                  "AND effective_from<=? AND (effective_to IS NULL OR effective_to>?)"):
        for orden, (valor, nombre) in enumerate(_DENOMINACIONES):
            conn.execute(
                "INSERT INTO cash_denominations (id, currency_code, denomination_value,"
                " display_name, sort_order, active, effective_from, effective_to)"
                " VALUES (?, 'MXN', ?, ?, ?, 1, ?, NULL)",
                (new_uuid(), valor, nombre, orden, _DESDE))
        sembrado["denominaciones"] = len(_DENOMINACIONES)

    if _tabla(conn, "cash_movement_reasons"):
        n = 0
        for codigo, nombre, tipo, autoriza in _MOTIVOS:
            if _vigente(conn, "SELECT 1 FROM cash_movement_reasons WHERE code=? AND active=1 "
                              "AND effective_from<=? AND (effective_to IS NULL OR effective_to>?)",
                        (codigo,)):
                continue
            conn.execute(
                "INSERT INTO cash_movement_reasons (id, code, display_name, movement_type,"
                " requires_authorization, active, effective_from, effective_to)"
                " VALUES (?,?,?,?,?,1,?,NULL)",
                (new_uuid(), codigo, nombre, tipo, autoriza, _DESDE))
            n += 1
        sembrado["motivos"] = n

    creador = _creador(conn)
    if _tabla(conn, "cash_operation_limits") and creador:
        n = 0
        for operacion, umbral, tope in _LIMITES:
            if _vigente(conn, "SELECT 1 FROM cash_operation_limits WHERE operation_type=? "
                              "AND effective_from<=? AND (effective_to IS NULL OR effective_to>?)",
                        (operacion,)):
                continue
            conn.execute(
                "INSERT INTO cash_operation_limits (id, operation_type, approval_threshold,"
                " hard_cap, scope_type, scope_id, effective_from, effective_to, created_by)"
                " VALUES (?,?,?,?, 'SYSTEM', NULL, ?, NULL, ?)",
                (new_uuid(), operacion, umbral, tope, _DESDE, creador))
            n += 1
        sembrado["limites"] = n

    if _tabla(conn, "cash_difference_policies") and not _vigente(
            conn, "SELECT 1 FROM cash_difference_policies WHERE active=1 "
                  "AND effective_from<=? AND (effective_to IS NULL OR effective_to>?)"):
        tolerancia, critica, ventana, reincidencia, canales = _TOLERANCIA
        conn.execute(
            "INSERT INTO cash_difference_policies (id, tolerance_amount, critical_threshold,"
            " recurrence_window_days, recurrence_threshold, channels_json, scope_type,"
            " scope_id, active, effective_from, effective_to)"
            " VALUES (?,?,?,?,?,?, 'SYSTEM', NULL, 1, ?, NULL)",
            (new_uuid(), tolerancia, critica, ventana, reincidencia,
             json.dumps(list(canales)), _DESDE))
        sembrado["tolerancia"] = 1
    conn.commit()
    logger.info("307: catálogos de Caja sembrados: %s", sembrado or "nada (ya existían)")


up = run
