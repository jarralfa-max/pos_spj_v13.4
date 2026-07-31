"""Runtime procurement authorization uses the canonical live session."""

import pytest

from backend.application.procurement.session_authorization import (
    ProcurementSessionPermissionChecker,
)
from frontend.desktop.modules.purchasing.enterprise_presenter import (
    EnterprisePurchasingPresenter,
)


class Session:
    is_active = True
    user_id = "user-1"
    active_branch_id = "branch-1"

    def tiene_permiso(self, code):
        return code == "PURCHASES_DIRECT_CREATE"

    def set_warehouse(self, warehouse_id, name=""):
        self.active_warehouse_id = warehouse_id
        self.active_warehouse_name = name


class Warehouses:
    def active_for_branch(self, branch_id):
        assert branch_id == "branch-1"
        return [("warehouse-1", "Principal")]


def test_live_session_requires_matching_actor_branch_and_permission():
    checker = ProcurementSessionPermissionChecker(Session())
    assert checker.has_permission("user-1", "PURCHASES_DIRECT_CREATE")
    assert not checker.has_permission("other", "PURCHASES_DIRECT_CREATE")
    assert not checker.has_permission("user-1", "PURCHASES_ORDER_APPROVE")


def test_inactive_or_branchless_session_denies():
    inactive = Session()
    inactive.is_active = False
    assert not ProcurementSessionPermissionChecker(inactive).has_permission(
        "user-1", "PURCHASES_DIRECT_CREATE")
    branchless = Session()
    branchless.active_branch_id = ""
    assert not ProcurementSessionPermissionChecker(branchless).has_permission(
        "user-1", "PURCHASES_DIRECT_CREATE")


def test_desktop_shell_can_render_without_inventing_a_warehouse():
    session = Session()
    session.nombre_completo = "Comprador Uno"
    presenter = EnterprisePurchasingPresenter(
        connection_provider=lambda: None, read_services={}, analytics=None,
        use_cases={}, session_context=session, warehouse_directory=Warehouses())

    summary = presenter.session_summary()

    assert summary == {
        "user": "Comprador Uno", "branch": "branch-1",
        "warehouse": "Sin almacén seleccionado", "warehouse_selected": False,
    }
    with pytest.raises(PermissionError, match="almacén activo"):
        presenter.default_warehouse()

    presenter.select_warehouse("warehouse-1")
    assert presenter.default_warehouse() == "warehouse-1"


def test_desktop_rejects_warehouse_outside_active_branch():
    presenter = EnterprisePurchasingPresenter(
        connection_provider=lambda: None, read_services={}, analytics=None,
        use_cases={}, session_context=Session(), warehouse_directory=Warehouses())
    with pytest.raises(PermissionError, match="no pertenece"):
        presenter.select_warehouse("warehouse-other")
