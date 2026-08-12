# migrations/standalone/179_inventario_canonical_permissions.py
"""
179 — Inventario adopta el catálogo granular `INVENTARIO.accion`.

Antes de esta migración `CANONICAL_MODULE_PERMISSIONS["INVENTARIO"]` era un
stub de 3 acciones gruesas (`ver`, `ajustar`, `transferir`) y
`InventoryPermissions` razonaba en códigos ingleses `INVENTORY_*` traducidos en
tiempo de ejecución por `InventorySessionPermissionChecker.legacy_codes_for()`
(un puente canónico→legacy que concedía CUALQUIER mutación granular a quien
tuviera el permiso legacy grueso `inventario.editar`, y CUALQUIER lectura a
quien tuviera `inventario.ver`). Esa traducción ya no existe: el catálogo y el
checker ahora comparten directamente el vocabulario granular `INVENTARIO.accion`
(ver `core/security/permission_catalog.py` y
`backend/application/inventory/permissions.py`).

Esta migración es defensiva y documental, igual que la 177 (Compras/Logística):

  1. Si por algún ajuste manual existiera una fila con `modulo='INVENTORY'`
     (forma inglesa), la normaliza a la canónica `'INVENTARIO'` SIN cambiar
     `accion` ni `permitido`.
  2. La acción `ver` del stub anterior sigue siendo válida tal cual (el nuevo
     catálogo también usa `INVENTARIO.ver`) — no requiere reescritura.
  3. Las acciones gruesas retiradas del stub anterior (`ajustar`, `transferir`)
     y el permiso legacy `inventario.editar` NO se expanden automáticamente a
     las ~70 acciones granulares nuevas — eso sería escalamiento de
     privilegios (§13 del contrato). Esas filas quedan tal cual (inertes: ya
     no coinciden con ningún `INVENTARIO.accion` real) y no se insertan filas
     nuevas.

Un administrador debe otorgar explícitamente las acciones granulares de
Inventario que un rol necesite vía Configuración → Seguridad → Permisos (ya
alimentado desde `CANONICAL_MODULE_PERMISSIONS`). Roles que dependían del
`inventario.editar`/`inventario.ajustar`/`inventario.transferir` legacy grueso
pierden esas acciones específicas hasta que se les re-otorguen los códigos
granulares nuevos — es un endurecimiento de mínimo privilegio intencional, no
una regresión.
"""
from __future__ import annotations

import sqlite3

DESCRIPTION = "Inventario: catálogo granular al formato canónico INVENTARIO.accion"

_LEGACY_MODULE_ALIASES = {
    "INVENTORY": "INVENTARIO",
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
