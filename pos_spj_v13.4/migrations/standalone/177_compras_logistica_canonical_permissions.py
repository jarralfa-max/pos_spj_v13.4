# migrations/standalone/177_compras_logistica_canonical_permissions.py
"""
177 — Compras/Logística adoptan el formato canónico `MODULO.accion`.

Antes de esta migración, `PurchasePermissions` usaba códigos planos tipo
`PURCHASES_REQUISITION_CREATE` y `LogisticsPermissions` usaba
`logistics.shipment.view` — ninguno de los dos con el formato `MODULO.accion`
que usa el resto del sistema (`FINANZAS.asiento.crear`, `ventas.cancelar`, …) y
que `rol_permisos`/`usuario_permisos`/`usuario_sucursal_permisos` esperan como
`(modulo, accion)`. Como ningún seed ni migración anterior insertó jamás filas
con esa forma para Compras/Logística granular (confirmado: solo existen las
filas gruesas `COMPRAS.{ver,crear,editar,eliminar,exportar}` de
`m000_base_schema.py::_seed_system_roles`), no hay privilegios reales que
migrar — cada verificación granular fallaba cerrado para todo rol no-admin.

Esta migración es defensiva y documental:
  1. Si por algún ajuste manual existiera una fila con `modulo` en su forma
     legacy ('PURCHASES', 'LOGISTICS'), la normaliza a la canónica
     ('COMPRAS', 'LOGISTICA') SIN cambiar `accion` ni `permitido` — preserva
     la intención de la fila tal cual estaba, no crea ni amplía permisos.
  2. No inserta ninguna fila nueva. Un administrador debe otorgar
     explícitamente las acciones granulares de Compras/Logística vía
     Configuración → Seguridad → Permisos (ya alimentado desde
     CANONICAL_MODULE_PERMISSIONS, que esta migración de código —
     core/security/permission_catalog.py — ya extendió).
"""
from __future__ import annotations

import sqlite3

DESCRIPTION = "Compras/Logística: permisos granulares al formato canónico MODULO.accion"

_LEGACY_MODULE_ALIASES = {
    "PURCHASES": "COMPRAS",
    "LOGISTICS": "LOGISTICA",
}

_PERMISSION_TABLES = ("rol_permisos", "usuario_permisos", "usuario_sucursal_permisos")


def _table_exists(conn: sqlite3.Connection, name: str) -> bool:
    return bool(conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,)
    ).fetchone())


def run(conn: sqlite3.Connection) -> None:
    for table in _PERMISSION_TABLES:
        if not _table_exists(conn, table):
            continue
        for legacy, canonical in _LEGACY_MODULE_ALIASES.items():
            conn.execute(
                f"UPDATE {table} SET modulo=? WHERE modulo=?", (canonical, legacy))
    conn.commit()
