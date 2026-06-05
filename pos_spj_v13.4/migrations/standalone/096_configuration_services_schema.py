"""096_configuration_services_schema.py — configuration schema ownership.

Moves configuration module schema/default bootstrapping out of PyQt and into
migrations so services and UI never create tables at runtime.
"""
from __future__ import annotations

import sqlite3

from core.module_config import DEFAULT_TOGGLES


def run(conn: sqlite3.Connection) -> None:
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
