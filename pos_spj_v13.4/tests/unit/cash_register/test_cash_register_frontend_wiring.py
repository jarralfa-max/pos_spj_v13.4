from backend.application.cash_register.permissions import CashPermissions
from frontend.desktop.modules.cash_register.cash_register_presenter import (
    CashRegisterPresenter,
    resolve_cash_register_capabilities,
)
from frontend.desktop.modules.cash_register.cash_register_routes import CASH_REGISTER_ROUTES


class _Session:
    is_active = True
    user_id = "user-1"
    active_branch_id = "branch-1"

    def __init__(self, grants):
        self._grants = set(grants)

    def tiene_permiso(self, code):
        return code in self._grants


class _Container:
    def __init__(self, session):
        self.session = session
        self.cash_configuration_query_service = object()
        self.cash_open_shift_uc = object()


def test_cash_routes_use_backend_permission_catalog():
    codes = {route.required_permission for route in CASH_REGISTER_ROUTES}
    assert CashPermissions.ACCESS in codes
    assert CashPermissions.SETTINGS_VIEW in codes
    assert all(code.startswith("CAJA.") for code in codes)
    assert not any(code.startswith("CASH_") or code.startswith("cash_register.") for code in codes)


def test_cash_presenter_resolves_capabilities_from_session_permissions():
    grants = {CashPermissions.ACCESS, CashPermissions.SETTINGS_VIEW}
    capabilities = resolve_cash_register_capabilities(_Session(grants).tiene_permiso)
    assert capabilities.module_view
    assert capabilities.configuration_view
    assert not capabilities.ledger_view


def test_cash_presenter_exposes_backend_query_services_from_container():
    presenter = CashRegisterPresenter(container=_Container(_Session({CashPermissions.ACCESS})))
    assert presenter.query_service("configuration") is not None
    assert presenter.query_service("ledger") is None
    assert "cash_open_shift_uc" in presenter.backend_binding("shifts")
