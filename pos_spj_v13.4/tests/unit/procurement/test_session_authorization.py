"""Runtime procurement authorization uses the canonical live session."""

from decimal import Decimal

import pytest

from backend.application.procurement.session_authorization import (
    ProcurementSessionPermissionChecker,
)
from backend.application.procurement.permissions import PurchasePermissions
from frontend.desktop.modules.purchasing.enterprise_presenter import (
    EnterprisePurchasingPresenter,
)
from frontend.desktop.modules.purchasing.direct_purchase_presenter import (
    DirectPurchasePresenter,
)
from frontend.desktop.modules.purchasing.direct_purchase_view_models import CartLineVM


class Session:
    is_active = True
    user_id = "user-1"
    active_branch_id = "branch-1"
    sucursal_nombre = "Sucursal Centro"

    def tiene_permiso(self, code):
        return code == PurchasePermissions.DIRECT_CREATE

    def set_warehouse(self, warehouse_id, name=""):
        self.active_warehouse_id = warehouse_id
        self.active_warehouse_name = name


class Warehouses:
    def active_for_branch(self, branch_id):
        assert branch_id == "branch-1"
        return [("warehouse-1", "Principal")]


def test_live_session_requires_matching_actor_branch_and_permission():
    checker = ProcurementSessionPermissionChecker(Session())
    assert checker.has_permission("user-1", PurchasePermissions.DIRECT_CREATE)
    assert not checker.has_permission("other", PurchasePermissions.DIRECT_CREATE)
    assert not checker.has_permission("user-1", PurchasePermissions.ORDER_APPROVE)


def test_inactive_or_branchless_session_denies():
    inactive = Session()
    inactive.is_active = False
    assert not ProcurementSessionPermissionChecker(inactive).has_permission(
        "user-1", PurchasePermissions.DIRECT_CREATE)
    branchless = Session()
    branchless.active_branch_id = ""
    assert not ProcurementSessionPermissionChecker(branchless).has_permission(
        "user-1", PurchasePermissions.DIRECT_CREATE)


def test_desktop_shell_can_render_without_inventing_a_warehouse():
    session = Session()
    session.nombre_completo = "Comprador Uno"
    presenter = EnterprisePurchasingPresenter(
        connection_provider=lambda: None, read_services={}, analytics=None,
        use_cases={}, session_context=session, warehouse_directory=Warehouses())

    summary = presenter.session_summary()

    assert summary == {
        "user": "Comprador Uno", "branch": "Sucursal Centro",
        "warehouse": "Sin almacén seleccionado", "warehouse_selected": False,
    }
    assert "branch-1" not in summary["branch"]  # never the raw UUID/id
    with pytest.raises(PermissionError, match="almacén activo"):
        presenter.default_warehouse()

    presenter.select_warehouse("warehouse-1")
    assert presenter.default_warehouse() == "warehouse-1"
    # once a warehouse is selected, the summary shows its name, not the id
    assert presenter.session_summary()["warehouse"] == "Principal"


def test_session_summary_degrades_gracefully_without_crashing_when_branch_unnamed():
    class UnnamedBranchSession(Session):
        sucursal_nombre = ""

    presenter = EnterprisePurchasingPresenter(
        connection_provider=lambda: None, read_services={}, analytics=None,
        use_cases={}, session_context=UnnamedBranchSession(), warehouse_directory=Warehouses())
    summary = presenter.session_summary()
    assert summary["branch"] == "Sucursal sin nombre configurado"
    assert "branch-1" not in summary["branch"]


def test_desktop_rejects_warehouse_outside_active_branch():
    presenter = EnterprisePurchasingPresenter(
        connection_provider=lambda: None, read_services={}, analytics=None,
        use_cases={}, session_context=Session(), warehouse_directory=Warehouses())
    with pytest.raises(PermissionError, match="no pertenece"):
        presenter.select_warehouse("warehouse-other")


def _direct_presenter(session):
    return DirectPurchasePresenter(
        connection_provider=lambda: None, read_service=None, supplier_picker=None,
        use_cases={}, session_context=session)


def test_direct_purchase_requires_canonical_session_scope():
    session = Session()
    presenter = _direct_presenter(session)

    assert presenter._actor() == "user-1"
    assert presenter.default_branch() == "branch-1"
    with pytest.raises(PermissionError, match="almacén activo"):
        presenter.default_warehouse()

    session.set_warehouse("warehouse-1", "Principal")
    assert presenter.default_warehouse() == "warehouse-1"


@pytest.mark.parametrize(
    ("attribute", "message"),
    [("user_id", "sesión autenticada"), ("active_branch_id", "sucursal activa")],
)
def test_direct_purchase_never_invents_missing_identity(attribute, message):
    session = Session()
    setattr(session, attribute, "")
    presenter = _direct_presenter(session)
    accessor = presenter._actor if attribute == "user_id" else presenter.default_branch

    with pytest.raises(PermissionError, match=message):
        accessor()


def test_direct_purchase_create_returns_actionable_block_when_warehouse_missing():
    presenter = _direct_presenter(Session())
    line = CartLineVM(
        product_id="product-1", description="Producto",
        quantity=Decimal("1"), unit_cost=Decimal("10"))

    ok, message, data = presenter.create(
        supplier_id="supplier-1", lines=[line], mode="IMMEDIATE",
        payment_condition="CASH")

    assert not ok
    assert message == "La sesión no tiene un almacén activo"
    assert data == {"error_code": "SESSION_CONTEXT_REQUIRED"}


def test_enterprise_capabilities_use_canonical_permission_constants():
    session = Session()
    session.tiene_permiso = lambda code: code in {
        PurchasePermissions.VIEW,
        PurchasePermissions.REQUISITION_VIEW,
        PurchasePermissions.REQUISITION_CREATE,
        PurchasePermissions.ORDER_VIEW,
    }
    presenter = EnterprisePurchasingPresenter(
        connection_provider=lambda: None, read_services={}, analytics=None,
        use_cases={}, session_context=session)

    capabilities = presenter.capabilities()

    assert capabilities.requisition_view
    assert capabilities.module_view
    assert capabilities.requisition_create
    assert capabilities.order_view
    assert not capabilities.order_create
    assert not capabilities.invoice_view


def test_direct_purchase_capabilities_are_fail_closed():
    session = Session()
    session.tiene_permiso = lambda code: code == PurchasePermissions.DIRECT_VIEW

    capabilities = _direct_presenter(session).capabilities()

    assert capabilities.direct_view
    assert not capabilities.direct_create
    assert not capabilities.direct_authorize
    assert not capabilities.direct_confirm
    assert not capabilities.direct_reverse
