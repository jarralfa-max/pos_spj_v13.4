"""Configurar un parámetro gobernado en una prueba, por la ruta canónica.

Sustituye a los `INSERT INTO configuraciones (...)` que sembraban parámetros
antes de SET-26: hoy un parámetro sólo cambia por `GovernedSettingsWriter`, y
una prueba que escribiera la tabla vieja no cambiaría nada.

Funciona sobre cualquier base de prueba: si faltan las tablas de gobierno
(bases armadas a mano), las crea con sus migraciones (208 y 224) y sincroniza
el catálogo.
"""

from __future__ import annotations

import importlib

from backend.application.settings.catalog import sync_configuration_catalog
from backend.application.settings.governance import GovernedSettingsWriter
from backend.domain.settings.enums import ScopeType
from backend.shared.ids import new_uuid

_SCHEMA_MIGRATIONS = (
    "migrations.standalone.208_settings_configuration_governance_schema",
    "migrations.standalone.224_configuracion_security_schema",
)


def ensure_governance(conn) -> None:
    for name in _SCHEMA_MIGRATIONS:
        module = importlib.import_module(name)
        (getattr(module, "run", None) or module.up)(conn)
    sync_configuration_catalog(conn)
    conn.commit()


def set_setting(conn, key: str, value, *, scope_type: ScopeType = ScopeType.GLOBAL,
                scope_id: str | None = None, actor_user_id: str | None = None) -> None:
    ensure_governance(conn)
    writer = GovernedSettingsWriter(conn)
    writer.stage({key: value}, actor_user_id=actor_user_id or new_uuid(),
                 reason="prueba", operation_id=new_uuid(), scope_type=scope_type,
                 scope_id=scope_id)
    conn.commit()
    writer.publish()
