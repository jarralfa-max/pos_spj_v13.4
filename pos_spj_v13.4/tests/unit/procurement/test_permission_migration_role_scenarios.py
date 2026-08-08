"""Regression coverage for the Compras/Logística canonical `MODULO.accion`
permission migration (migration 177). See migrations/MIGRATION_LOG.md.

Covers, per role, exactly the scenarios required by the migration:
  1. comprador sees only solicitudes/órdenes/compra directa autorizadas
  2. aprobador puede aprobar pero no capturar operaciones no autorizadas
  3. receptor puede recibir pero no aprobar órdenes (enforced en backend)
  4. sin COMPRAS.ver, el usuario no entra al módulo (rutas vacías)
  7. backend y UI producen el mismo resultado de autorización
  8. una sesión sin sucursal activa falla de forma cerrada

Scenarios 5 (rutas aparecen tras login/refresh) and 6 (cambios de permisos se
reflejan sin reiniciar) require a real PyQt shell and live in
tests/integration/procurement/test_enterprise_ui.py.
"""

import pytest

from backend.application.logistics.authorization import LogisticsPermissions
from backend.application.procurement.authorization import PurchaseAuthorizationPolicy
from backend.application.procurement.permissions import PurchasePermissions
from backend.application.procurement.session_authorization import (
    ProcurementSessionPermissionChecker,
)
from backend.domain.procurement.exceptions import PurchasePermissionDeniedError
from frontend.desktop.modules.purchasing.enterprise_presenter import (
    EnterprisePurchasingPresenter,
)
from frontend.desktop.modules.purchasing.navigation import PurchasingRoutes, visible_routes


class _Session:
    active_branch_id = "branch-1"
    active_warehouse_id = "warehouse-1"

    def __init__(self, grants, *, user_id="role-user", is_active=True, active_branch_id="branch-1"):
        self._grants = grants
        self.user_id = user_id
        self.is_active = is_active
        self.active_branch_id = active_branch_id

    def tiene_permiso(self, permission):
        return permission in self._grants


def _presenter(session):
    return EnterprisePurchasingPresenter(
        connection_provider=lambda: None, read_services={}, analytics=None,
        use_cases={}, session_context=session)


# ── 1. comprador ve únicamente solicitudes, órdenes y compra directa ────────
def test_comprador_sees_only_requisitions_orders_and_direct_purchase():
    grants = {
        PurchasePermissions.VIEW, PurchasePermissions.REQUISITION_VIEW,
        PurchasePermissions.REQUISITION_CREATE, PurchasePermissions.ORDER_VIEW,
        PurchasePermissions.ORDER_CREATE, PurchasePermissions.ORDER_SEND,
        PurchasePermissions.DIRECT_VIEW, PurchasePermissions.DIRECT_CREATE,
    }
    caps = _presenter(_Session(grants)).capabilities()
    routes = {route.key for route in visible_routes(caps)}
    assert routes == {
        PurchasingRoutes.DASHBOARD, PurchasingRoutes.REQUISITIONS,
        PurchasingRoutes.ORDERS, PurchasingRoutes.DIRECT_PURCHASE_CREATE,
        PurchasingRoutes.DIRECT_PURCHASE_HISTORY,
    }
    # no ve recepciones, facturas ni compra en origen
    assert PurchasingRoutes.RECEIPTS not in routes
    assert PurchasingRoutes.INVOICES not in routes
    assert PurchasingRoutes.ORIGIN_LOADING not in routes


# ── 2. aprobador aprueba, pero no captura operaciones no autorizadas ────────
def test_aprobador_can_approve_but_not_capture_unauthorized_operations():
    grants = {
        PurchasePermissions.VIEW, PurchasePermissions.REQUISITION_VIEW,
        PurchasePermissions.REQUISITION_APPROVE, PurchasePermissions.ORDER_VIEW,
        PurchasePermissions.ORDER_APPROVE,
    }
    caps = _presenter(_Session(grants)).capabilities()
    assert caps.requisition_approve and caps.order_approve
    # sin las acciones granulares correspondientes, no puede capturar/crear
    assert not caps.invoice_capture
    assert not caps.direct_create
    assert not caps.requisition_create
    checker = ProcurementSessionPermissionChecker(_Session(grants))
    policy = PurchaseAuthorizationPolicy(checker)
    policy.require("role-user", PurchasePermissions.ORDER_APPROVE)  # no lanza
    with pytest.raises(PurchasePermissionDeniedError):
        policy.require("role-user", PurchasePermissions.INVOICE_CAPTURE)


# ── 3. receptor recibe, pero no aprueba órdenes (backend fail-closed) ───────
def test_receptor_can_receive_but_not_approve_orders():
    grants = {
        PurchasePermissions.VIEW, PurchasePermissions.ORDER_VIEW,
        PurchasePermissions.RECEIPT_VIEW, PurchasePermissions.RECEIPT_COMPLETE,
    }
    caps = _presenter(_Session(grants)).capabilities()
    assert caps.receipt_complete
    assert not caps.order_approve
    checker = ProcurementSessionPermissionChecker(_Session(grants))
    policy = PurchaseAuthorizationPolicy(checker)
    policy.require("role-user", PurchasePermissions.RECEIPT_COMPLETE)  # no lanza
    with pytest.raises(PurchasePermissionDeniedError):
        policy.require("role-user", PurchasePermissions.ORDER_APPROVE)


# ── 4. sin COMPRAS.ver, el usuario no entra al módulo ───────────────────────
def test_user_without_module_view_sees_no_routes():
    caps = _presenter(_Session(set())).capabilities()
    assert not caps.module_view
    assert visible_routes(caps) == ()


def test_logistica_role_uses_logistica_permissions_not_purchases():
    grants = {
        PurchasePermissions.VIEW, LogisticsPermissions.SHIPMENT_VIEW,
        LogisticsPermissions.SHIPMENT_CREATE, LogisticsPermissions.CONTAINER_SEAL,
    }
    caps = _presenter(_Session(grants)).capabilities()
    assert caps.origin_view and caps.origin_create and caps.origin_seal
    assert not caps.origin_dispatch and not caps.origin_override
    routes = {route.key for route in visible_routes(caps)}
    assert routes == {PurchasingRoutes.DASHBOARD, PurchasingRoutes.ORIGIN_LOADING}


# ── 7. backend y UI producen el mismo resultado de autorización ────────────
@pytest.mark.parametrize("code", [
    PurchasePermissions.REQUISITION_CREATE, PurchasePermissions.ORDER_APPROVE,
    PurchasePermissions.DIRECT_CREATE, PurchasePermissions.RECEIPT_COMPLETE,
    PurchasePermissions.INVOICE_MATCH, LogisticsPermissions.SHIPMENT_DISPATCH,
])
@pytest.mark.parametrize("granted", [True, False])
def test_backend_and_ui_authorization_agree(code, granted):
    grants = {code} if granted else set()
    session = _Session(grants)
    ui_result = session.tiene_permiso(code)
    backend_result = ProcurementSessionPermissionChecker(session).has_permission(
        session.user_id, code)
    assert ui_result == granted
    assert backend_result == granted
    assert ui_result == backend_result


# ── 8. sesión sin sucursal activa falla de forma cerrada ────────────────────
def test_session_without_active_branch_fails_closed():
    session = _Session({PurchasePermissions.DIRECT_CREATE}, active_branch_id="")
    assert session.tiene_permiso(PurchasePermissions.DIRECT_CREATE)  # UI-side: concede
    # pero el backend exige sucursal activa y niega pese al permiso concedido
    checker = ProcurementSessionPermissionChecker(session)
    assert not checker.has_permission(session.user_id, PurchasePermissions.DIRECT_CREATE)
    policy = PurchaseAuthorizationPolicy(checker)
    with pytest.raises(PurchasePermissionDeniedError):
        policy.require(session.user_id, PurchasePermissions.DIRECT_CREATE)


def test_inactive_session_fails_closed_even_with_grant():
    session = _Session({PurchasePermissions.DIRECT_CREATE}, is_active=False)
    checker = ProcurementSessionPermissionChecker(session)
    assert not checker.has_permission(session.user_id, PurchasePermissions.DIRECT_CREATE)
