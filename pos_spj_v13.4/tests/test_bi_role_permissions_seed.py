"""Las secciones del tablero BI exigen códigos que el catálogo puede conceder.

Las dos pruebas de los permisos «por defecto» por rol se retiraron con
`security/rbac.py` (auditoría de permisos 968e0bc, PER-05): probaban la matriz
hardcodeada de un RBAC paralelo que ningún código de producción usaba.
"""
from backend.application.analytics.services.bi_dashboard_service import SECTION_PERMISSION
from backend.application.security.permission_catalog import CANONICAL_MODULE_PERMISSIONS


def test_section_permissions_existen_en_catalogo():
    acciones = set(CANONICAL_MODULE_PERMISSIONS["INTELIGENCIA_BI"])
    for code in SECTION_PERMISSION.values():
        _, accion = code.split(".", 1)
        assert accion in acciones
