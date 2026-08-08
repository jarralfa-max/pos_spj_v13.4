# migrations/standalone/178_proveedores_bloqueo_financiero.py
"""
178 — Bloqueo financiero real de proveedores (proveedores.bloqueado_financiero).

Compras (SupplierDirectoryQueryService.get_eligibility) devolvía
`purchasing_enabled=True` y `financially_blocked=False` como valores fijos
porque `proveedores` no tenía ninguna columna que representara un bloqueo
financiero — solo existía `activo`. Un proveedor con adeudo vencido o
suspendido por Finanzas no podía marcarse como no-comprable; la validación de
elegibilidad siempre pasaba.

Esta migración solo agrega las columnas (idempotente, DEFAULT 0/NULL — no
bloquea a nadie que hoy no estuviera bloqueado, ningún dato existente cambia
de estado). La UI/flujo para que un usuario autorizado marque el bloqueo
queda pendiente de diseño (quién puede bloquear/desbloquear y desde qué
módulo); esta migración solo habilita que el dato pueda existir y leerse.
"""
from __future__ import annotations

import logging

logger = logging.getLogger("spj.migrations.178")


def _column_exists(conn, table: str, column: str) -> bool:
    return any(r[1] == column for r in conn.execute(f"PRAGMA table_info({table})"))


def run(conn) -> None:
    if not _column_exists(conn, "proveedores", "bloqueado_financiero"):
        conn.execute(
            "ALTER TABLE proveedores ADD COLUMN bloqueado_financiero INTEGER DEFAULT 0")
    if not _column_exists(conn, "proveedores", "motivo_bloqueo"):
        conn.execute("ALTER TABLE proveedores ADD COLUMN motivo_bloqueo TEXT")
    if not _column_exists(conn, "proveedores", "compras_habilitadas"):
        conn.execute(
            "ALTER TABLE proveedores ADD COLUMN compras_habilitadas INTEGER DEFAULT 1")
    conn.commit()
    logger.info("178: proveedores.bloqueado_financiero/motivo_bloqueo/compras_habilitadas aseguradas.")


up = run
