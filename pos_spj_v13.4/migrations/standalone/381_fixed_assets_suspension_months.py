"""381 — Meses fuera de servicio de un activo fijo (SDLC-FIN-003).

Los meses omitidos de depreciación ahora se recuperan en la siguiente corrida
(decisión del responsable, 2026-11-05). Un mes suspendido no es un mes omitido:
hay que distinguirlos, y antes sólo quedaba el estado actual.

Sólo agrega dos columnas. Idempotente.
"""

from __future__ import annotations


def run(conn) -> None:
    tiene_tabla = conn.execute("SELECT 1 FROM sqlite_master WHERE type='table'"
                               " AND name='fixed_assets'").fetchone()
    if tiene_tabla is None:
        return  # base sin Finanzas: el DDL born-clean ya trae las columnas
    columnas = {str(r[1]) for r in conn.execute("PRAGMA table_info(fixed_assets)")}
    if "suspended_on" not in columnas:
        conn.execute("ALTER TABLE fixed_assets ADD COLUMN suspended_on TEXT")
    if "suspended_months" not in columnas:
        conn.execute("ALTER TABLE fixed_assets"
                     " ADD COLUMN suspended_months INTEGER NOT NULL DEFAULT 0")


up = run
