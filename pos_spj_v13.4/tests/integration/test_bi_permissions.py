"""FASE 13 — el dashboard respeta permisos por sección."""
from backend.application.dto.bi_dashboard_dto import DashboardFilters
from backend.application.queries.bi_dashboard_query_service import BiDashboardQueryService
from backend.application.services.bi_dashboard_service import BiDashboardService
from tests.integration import bi_seed as S


def _service(permission_checker):
    conn = S.fresh_db()
    b = S.add_branch(conn)
    p = S.add_product(conn, "Pollo", "Aves", 18.0, branch_id=b)
    S.add_sale(conn, b, [(p, 1, 30.0, 18.0)], when=S.this_month_day())
    conn.commit()
    return BiDashboardService(BiDashboardQueryService(conn),
                              permission_checker=permission_checker)


def test_dueno_ve_todas_las_secciones():
    svc = _service(lambda perm: True)
    secs = svc.build_dashboard(DashboardFilters()).allowed_sections
    assert "finanzas" in secs and "proveedores" in secs and "configuracion" in secs


def test_cajero_sin_finanzas_no_ve_finanzas():
    svc = _service(lambda perm: perm != "INTELIGENCIA_BI.ver_finanzas")
    secs = svc.build_dashboard(DashboardFilters()).allowed_sections
    assert "finanzas" not in secs
    assert "resumen" in secs          # resumen siempre visible
    assert "ventas" in secs


def test_permisos_usan_codigos_del_catalogo():
    from core.security.permission_catalog import CANONICAL_MODULE_PERMISSIONS
    from backend.application.services.bi_dashboard_service import SECTION_PERMISSION
    acciones = set(CANONICAL_MODULE_PERMISSIONS["INTELIGENCIA_BI"])
    for code in SECTION_PERMISSION.values():
        modulo, accion = code.split(".", 1)
        assert modulo == "INTELIGENCIA_BI"
        assert accion in acciones, f"acción {accion} no está en el catálogo"


def test_usuario_limitado_solo_resumen():
    svc = _service(lambda perm: False)
    secs = svc.build_dashboard(DashboardFilters()).allowed_sections
    assert secs == ["resumen"]
