import sqlite3

from core.security.permission_catalog import CANONICAL_MODULE_PERMISSIONS
from repositories.config_repository import ConfigRepository


def test_permission_matrix_uses_catalog_even_when_role_permissions_empty() -> None:
    conn = sqlite3.connect(":memory:")
    conn.execute("CREATE TABLE rol_permisos(rol_id INTEGER, modulo TEXT, accion TEXT, permitido INTEGER)")

    matrix = dict(ConfigRepository(conn).permission_matrix())

    assert set(CANONICAL_MODULE_PERMISSIONS) <= set(matrix)
    assert "ver" in matrix["POS"]
    assert "ver" in matrix["CAJA"]
    assert "ver" in matrix["CONFIG_SEGURIDAD"]
    assert "ver" in matrix["CONFIG_MODULOS"]
