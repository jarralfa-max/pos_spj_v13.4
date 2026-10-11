"""320 — quien convierte cotizaciones puede crear el pedido (CRM-43, 2026-10-09).

POR QUÉ HACE FALTA (medido en una copia de la base viva)
-------------------------------------------------------
El usuario decidió que gerente y cajero conviertan en pedido las cotizaciones
aceptadas (migración 319, ``COTIZACIONES.convertir``). La conversión la hace el
caso de uso de Pedidos, que exige ``DELIVERY.pedido.crear``; en la base real
ningún rol lo tenía (gerente y cajero sólo traen los códigos gruesos del
sembrado base, ``DELIVERY.crear``/``ver``…, que Pedidos no revisa), así que
la conversión se rechazaba con «no tiene el permiso DELIVERY.pedido.crear».

Concede SÓLO ``pedido.crear`` a los roles que convierten (gerente, cajero). La
matriz completa de Pedidos por rol NO se siembra aquí: es otra decisión
(anotada en docs/refactor/CRM-43_reauditoria.md). Idempotente.
"""

from __future__ import annotations

import logging

from backend.shared.ids import new_uuid

logger = logging.getLogger("spj.migrations.320")

_ROLES = ("gerente", "cajero")


def run(conn) -> None:
    if conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='rol_permisos'"
                    ).fetchone() is None:
        return
    concedidos = 0
    for rol in _ROLES:
        fila = conn.execute("SELECT id FROM roles WHERE lower(trim(nombre))=?", (rol,)).fetchone()
        if fila is None:
            continue
        ya = conn.execute(
            "SELECT 1 FROM rol_permisos WHERE rol_id=? AND upper(modulo)='DELIVERY'"
            " AND lower(accion)='pedido.crear'", (str(fila[0]),)).fetchone()
        if ya:
            continue
        conn.execute("INSERT INTO rol_permisos (id, rol_id, modulo, accion, permitido)"
                     " VALUES (?,?,?,?,1)", (new_uuid(), str(fila[0]), "DELIVERY", "pedido.crear"))
        concedidos += 1
    conn.commit()
    logger.info("320: DELIVERY.pedido.crear concedido a %s rol(es).", concedidos)


up = run
