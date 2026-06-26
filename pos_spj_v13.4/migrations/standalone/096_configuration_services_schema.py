"""096_configuration_services_schema.py — configuration schema ownership.

Moves configuration module schema/default bootstrapping out of PyQt and into
migrations so services and UI never create tables at runtime.
"""
from __future__ import annotations

import sqlite3

from backend.shared.ids import new_uuid
from core.module_config import DEFAULT_TOGGLES


def run(conn: sqlite3.Connection) -> None:
    def column_exists(table: str, column: str) -> bool:
        rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
        return any(str(row[1]) == column for row in rows)

    def add_column_if_missing(table: str, column_def: str) -> None:
        column_name = column_def.split()[0]
        if not column_exists(table, column_name):
            conn.execute(f"ALTER TABLE {table} ADD COLUMN {column_def}")

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS config_programa_fidelidad (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nombre_programa TEXT,
            puntos_por_peso DECIMAL(10,2) DEFAULT 1.0,
            niveles TEXT,
            requisitos TEXT,
            descuentos TEXT,
            activo INTEGER DEFAULT 1,
            fecha_creacion DATETIME DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    conn.execute(
        """
        INSERT INTO config_programa_fidelidad (id, nombre_programa, puntos_por_peso)
        VALUES (1, 'Programa de Puntos', 1.0)
        ON CONFLICT(id) DO NOTHING
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS module_toggles (
            clave TEXT PRIMARY KEY,
            activo INTEGER DEFAULT 1,
            descripcion TEXT DEFAULT ''
        )
        """
    )
    for table in ("sucursales", "usuarios", "roles", "happy_hour_rules", "cierre_mensual"):
        if conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)).fetchone():
            add_column_if_missing(table, "uuid TEXT")
    if conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='usuarios'").fetchone():
        add_column_if_missing("usuarios", "sucursal_uuid TEXT")
    if conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='happy_hour_rules'").fetchone():
        add_column_if_missing("happy_hour_rules", "sucursal_uuid TEXT")
    if conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='cierre_mensual'").fetchone():
        add_column_if_missing("cierre_mensual", "sucursal_uuid TEXT")
    if conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='rol_permisos'").fetchone():
        add_column_if_missing("rol_permisos", "rol_uuid TEXT")

    if conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='sucursales'").fetchone():
        rows = conn.execute("SELECT id FROM sucursales WHERE COALESCE(uuid, '') = ''").fetchall()
        for row in rows:
            conn.execute("UPDATE sucursales SET uuid=? WHERE id=?", (new_uuid(), row[0]))
    if conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='roles'").fetchone():
        rows = conn.execute("SELECT id FROM roles WHERE COALESCE(uuid, '') = ''").fetchall()
        for row in rows:
            conn.execute("UPDATE roles SET uuid=? WHERE id=?", (new_uuid(), row[0]))
    if conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='usuarios'").fetchone():
        rows = conn.execute("SELECT id, sucursal_id FROM usuarios WHERE COALESCE(uuid, '') = '' OR COALESCE(sucursal_uuid, '') = ''").fetchall()
        for row in rows:
            user_uuid = conn.execute("SELECT uuid FROM usuarios WHERE id=?", (row[0],)).fetchone()
            branch_uuid = conn.execute("SELECT uuid FROM sucursales WHERE id=?", (row[1],)).fetchone() if row[1] is not None else None
            conn.execute(
                "UPDATE usuarios SET uuid=COALESCE(NULLIF(uuid, ''), ?), sucursal_uuid=COALESCE(NULLIF(sucursal_uuid, ''), ?) WHERE id=?",
                (new_uuid() if not user_uuid or not user_uuid[0] else user_uuid[0], branch_uuid[0] if branch_uuid else "", row[0]),
            )
    if conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='happy_hour_rules'").fetchone():
        rows = conn.execute("SELECT id, sucursal_id FROM happy_hour_rules WHERE COALESCE(uuid, '') = '' OR COALESCE(sucursal_uuid, '') = ''").fetchall()
        for row in rows:
            branch_uuid = conn.execute("SELECT uuid FROM sucursales WHERE id=?", (row[1],)).fetchone() if row[1] is not None else None
            conn.execute(
                "UPDATE happy_hour_rules SET uuid=COALESCE(NULLIF(uuid, ''), ?), sucursal_uuid=COALESCE(NULLIF(sucursal_uuid, ''), ?) WHERE id=?",
                (new_uuid(), branch_uuid[0] if branch_uuid else "", row[0]),
            )
    if conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='cierre_mensual'").fetchone():
        rows = conn.execute("SELECT id, sucursal_id FROM cierre_mensual WHERE COALESCE(uuid, '') = '' OR COALESCE(sucursal_uuid, '') = ''").fetchall()
        for row in rows:
            branch_uuid = conn.execute("SELECT uuid FROM sucursales WHERE id=?", (row[1],)).fetchone() if row[1] is not None else None
            conn.execute(
                "UPDATE cierre_mensual SET uuid=COALESCE(NULLIF(uuid, ''), ?), sucursal_uuid=COALESCE(NULLIF(sucursal_uuid, ''), ?) WHERE id=?",
                (new_uuid(), branch_uuid[0] if branch_uuid else "", row[0]),
            )
    if conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='rol_permisos'").fetchone():
        rows = conn.execute("SELECT rowid, rol_id FROM rol_permisos WHERE COALESCE(rol_uuid, '') = ''").fetchall()
        for row in rows:
            role_uuid = conn.execute("SELECT uuid FROM roles WHERE id=?", (row[1],)).fetchone()
            conn.execute("UPDATE rol_permisos SET rol_uuid=? WHERE rowid=?", ((role_uuid[0] if role_uuid else ""), row[0]))

    for key, enabled in DEFAULT_TOGGLES.items():
        conn.execute(
            """
            INSERT INTO module_toggles(clave, activo)
            VALUES(?, ?)
            ON CONFLICT(clave) DO NOTHING
            """,
            (key, 1 if enabled else 0),
        )
    for key, value, description in (
        ("impuesto_por_defecto", "16.0", "Impuesto por defecto en porcentaje"),
        ("requerir_admin", "False", "Requerir administrador para acciones críticas"),
        ("tema", "Claro", "Tema de la aplicación"),
    ):
        conn.execute(
            """
            INSERT INTO configuraciones (clave, valor, descripcion)
            VALUES (?, ?, ?)
            ON CONFLICT(clave) DO NOTHING
            """,
            (key, value, description),
        )
    try:
        conn.commit()
    except Exception:
        pass


up = run
