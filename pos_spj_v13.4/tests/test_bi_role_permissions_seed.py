"""Los roles por defecto reciben los permisos del módulo BI (INTELIGENCIA_BI.*)."""
from backend.application.services.bi_dashboard_service import SECTION_PERMISSION
from core.security.permission_catalog import CANONICAL_MODULE_PERMISSIONS
from security.rbac import _get_default_permisos


def test_gerente_recibe_bi_completo():
    perms = _get_default_permisos("gerente")
    esperado = {f"INTELIGENCIA_BI.{a}" for a in CANONICAL_MODULE_PERMISSIONS["INTELIGENCIA_BI"]}
    assert esperado <= perms


def test_cajero_bi_limitado():
    perms = _get_default_permisos("cajero")
    assert "INTELIGENCIA_BI.ver_ventas" in perms
    assert "INTELIGENCIA_BI.ver_finanzas" not in perms


def test_section_permissions_existen_en_catalogo():
    acciones = set(CANONICAL_MODULE_PERMISSIONS["INTELIGENCIA_BI"])
    for code in SECTION_PERMISSION.values():
        _, accion = code.split(".", 1)
        assert accion in acciones
