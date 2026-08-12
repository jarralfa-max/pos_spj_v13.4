from backend.application.cash_register.permissions import ALL_CASH_PERMISSIONS, CashPermissions
from core.security.permission_catalog import CANONICAL_MODULE_PERMISSIONS, permission_code
from frontend.desktop.modules.cash_register.cash_register_routes import CASH_REGISTER_ROUTES


def test_cash_permissions_use_module_action_format():
    assert ALL_CASH_PERMISSIONS
    assert all(code.startswith("CAJA.") for code in ALL_CASH_PERMISSIONS)
    assert not any(code.startswith("CASH_") for code in ALL_CASH_PERMISSIONS)
    assert CashPermissions.ACCESS == "CAJA.ver"
    assert "CAJA.acceso" not in ALL_CASH_PERMISSIONS


def test_cash_permission_catalog_matches_permissions_one_to_one():
    catalog = {
        permission_code("CAJA", action)
        for action in CANONICAL_MODULE_PERMISSIONS["CAJA"]
    }
    assert catalog == set(ALL_CASH_PERMISSIONS)


def test_cash_routes_use_view_permissions_not_action_permissions():
    route_permissions = {route.key: route.required_permission for route in CASH_REGISTER_ROUTES}
    assert route_permissions["overview"] == CashPermissions.ACCESS
    assert route_permissions["blind_count"] == CashPermissions.BLIND_COUNT_VIEW
    assert route_permissions["handover"] == CashPermissions.HANDOVER_VIEW
    assert route_permissions["refunds"] == CashPermissions.REFUND_VIEW
    assert route_permissions["hardware"] == CashPermissions.HARDWARE_VIEW
    assert not route_permissions["blind_count"].endswith(".iniciar")
    assert not route_permissions["handover"].endswith(".preparar")
    assert not route_permissions["refunds"].endswith(".solicitar")
    assert not route_permissions["hardware"].endswith(".diagnosticar")


def test_cash_has_no_dispositivo_namespace():
    assert not any(".dispositivo." in code for code in ALL_CASH_PERMISSIONS)
