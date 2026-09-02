# bootstrap/lifecycle.py — WA-4
"""
Coordina el arranque/apagado del `WhatsAppCompositionRoot`: aplica el gate
de secretos de producción (WA-1), abre la conexión SQLite, construye el
CompositionRoot y lo valida (`dependency_graph_validator`).

No ejecuta migraciones — eso sigue siendo responsabilidad exclusiva de
`main.py::lifespan()` (una sola fuente de "quién corre las migraciones al
arrancar", sin duplicarlo aquí). Este módulo asume que el esquema ya
existe cuando se le da una ruta de base de datos.
"""
from __future__ import annotations

import sqlite3

from bootstrap.composition_root import WhatsAppCompositionRoot
from bootstrap.dependency_graph_validator import validate_composition_root


def start_composition_root(db_path: str) -> WhatsAppCompositionRoot:
    """Aplica el gate de producción, abre la conexión, construye y valida
    el CompositionRoot. El llamador es dueño del ciclo de vida de la
    conexión resultante — usar `stop_composition_root()` para cerrarla."""
    from config.settings import is_production
    from main import _assert_production_secrets_configured

    if is_production():
        _assert_production_secrets_configured()

    conn = sqlite3.connect(db_path, check_same_thread=False)
    root = WhatsAppCompositionRoot(conn)
    validate_composition_root(root)
    return root


def stop_composition_root(root: WhatsAppCompositionRoot) -> None:
    conn = root.registry.get("whatsapp_db_connection")
    conn.close()
