"""Biblioteca de logos para documentos impresos (comparativa de tickets, 2026-10-16).

`company_profiles.logo_asset_id` existía desde SET-5 apuntando a «un asset
registrado en otro sistema» que nunca existió: la pantalla pedía teclear un UUID
y no había dónde cargar una imagen. Esta es esa biblioteca.

* `branding_assets`: cada logo cargado — el ORIGINAL (nunca se destruye) y su
  derivado para impresión térmica (fondo quitado si se pidió, aplanado en
  blanco). §15: el perfil guarda la referencia al asset, no una ruta.
* `branch_branding`: el logo propio de una sucursal (decisión del usuario:
  empresa + sucursal opcional; sin el suyo, hereda el de la empresa).
"""

from __future__ import annotations

BRANDING_TABLES = ("branding_assets", "branch_branding")

_DDL = (
    """
    CREATE TABLE IF NOT EXISTS branding_assets (
        id                  TEXT NOT NULL PRIMARY KEY,
        kind                TEXT NOT NULL DEFAULT 'LOGO',
        original_path       TEXT NOT NULL,
        print_path          TEXT NOT NULL,
        background_removed  INTEGER NOT NULL DEFAULT 0,
        tolerance           TEXT,
        width_px            INTEGER,
        height_px           INTEGER,
        created_by_user_id  TEXT,
        created_at          TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS branch_branding (
        branch_id           TEXT NOT NULL PRIMARY KEY,
        logo_asset_id       TEXT REFERENCES branding_assets(id),
        updated_by_user_id  TEXT,
        updated_at          TEXT NOT NULL
    )
    """,
)


def create_branding_schema(conn) -> None:
    for statement in _DDL:
        conn.execute(statement)
