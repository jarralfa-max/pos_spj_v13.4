"""349 — Lotes físicos de cupones y vales (auditoría de Fidelidad 968e0bc,
ampliación «lotes físicos de vales y cupones, con canje configurable»).

Crea `instrument_batches`, `instrument_batch_items` (folio legible, huella del
token público por PIEZA), `voucher_instance_rules` (fotografía de las reglas de
canje de cada vale emitido por lote: un evento / varios, tope % por venta, base
del porcentaje, sobrante, origen de los fondos, sucursales y vigencia) y
`commercial_instrument_secrets` (secreto de la instalación para derivar los
tokens con HMAC, como las tarjetas de fidelidad).

Sólo tablas nuevas: ningún cupón o vale existente cambia de comportamiento. Un
vale sin fila de reglas sigue siendo saldo libre en varias ventas. Idempotente.

Siembra además las acciones nuevas `GROWTH_ENGINE.lote.*` con el criterio que
el usuario aprobó en la 290 (otorgable ≠ otorgado: sin siembra, nadie podría
usar la pantalla): `system_owner` y `admin` todo; `gerente` lo operativo —ver,
crear e imprimir—, no aprobar/activar/cancelar ni revocar piezas (revocar rota
el código, como `qr.rotar` en Tarjetas). Un rol que no exista se omite.
"""

from __future__ import annotations

import logging

from backend.shared.ids import new_uuid

logger = logging.getLogger("spj.migrations.349")

#: Foto fija de las acciones `lote.*` de `backend/application/loyalty/permissions.py`.
LOTES = ("lote.ver", "lote.crear", "lote.aprobar", "lote.imprimir", "lote.revocar")
_ASIGNACIONES = {
    "system_owner": LOTES,
    "admin": LOTES,
    "gerente": ("lote.ver", "lote.crear", "lote.imprimir"),
}


def _sembrar_permisos(conn) -> None:
    tablas = {r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name IN ('roles','rol_permisos')")}
    if tablas != {"roles", "rol_permisos"}:
        return
    for rol, acciones in _ASIGNACIONES.items():
        fila = conn.execute("SELECT id FROM roles WHERE lower(trim(nombre))=?",
                            (rol,)).fetchone()
        if fila is None:
            continue
        for accion in acciones:
            conn.execute(
                "INSERT OR IGNORE INTO rol_permisos (id, rol_id, modulo, accion, permitido)"
                " VALUES (?,?,?,?,1)", (new_uuid(), str(fila[0]), "GROWTH_ENGINE", accion))
    logger.info("349: acciones de lotes de cupones y vales sembradas")


def run(conn) -> None:
    _sembrar_permisos(conn)
    from backend.infrastructure.db.schema.commercial_instruments_schema import (
        create_instrument_batch_schema,
    )
    existe = conn.execute("SELECT 1 FROM sqlite_master WHERE type='table'"
                          " AND name='voucher_instances'").fetchone()
    if existe is None:
        return  # Instrumentos comerciales aún no instalado: su esquema completo lo incluye
    create_instrument_batch_schema(conn)
