import sqlite3

from repositories.config_repository import ConfigRepository


def test_permission_matrix_includes_catalog_when_role_permissions_empty() -> None:
    conn = sqlite3.connect(":memory:")
    conn.execute("CREATE TABLE rol_permisos(rol_id INTEGER, modulo TEXT, accion TEXT, permitido INTEGER)")

    matrix = dict(ConfigRepository(conn).permission_matrix())

    assert "ver" in matrix["POS"]
    assert "ver" in matrix["CAJA"]
    assert "ver" in matrix["CONFIG_SEGURIDAD"]
