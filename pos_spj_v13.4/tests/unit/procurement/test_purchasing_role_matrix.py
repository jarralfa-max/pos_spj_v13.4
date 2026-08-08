"""Closure matrix: desktop routes and actions remain least-privilege by role."""

import pytest

from backend.application.logistics.authorization import LogisticsPermissions
from backend.application.procurement.permissions import PurchasePermissions
from frontend.desktop.modules.purchasing.enterprise_presenter import EnterprisePurchasingPresenter
from frontend.desktop.modules.purchasing.navigation import PurchasingRoutes, visible_routes


ROLE_GRANTS = {
    "solicitante": {
        PurchasePermissions.VIEW, PurchasePermissions.REQUISITION_VIEW,
        PurchasePermissions.REQUISITION_CREATE, PurchasePermissions.REQUISITION_SUBMIT,
    },
    "comprador": {
        PurchasePermissions.VIEW, PurchasePermissions.REQUISITION_VIEW,
        PurchasePermissions.RFQ_CREATE, PurchasePermissions.ORDER_VIEW,
        PurchasePermissions.ORDER_CREATE, PurchasePermissions.ORDER_SEND,
        PurchasePermissions.DIRECT_VIEW, PurchasePermissions.DIRECT_CREATE,
    },
    "aprobador": {
        PurchasePermissions.VIEW, PurchasePermissions.REQUISITION_VIEW,
        PurchasePermissions.REQUISITION_APPROVE, PurchasePermissions.ORDER_VIEW,
        PurchasePermissions.ORDER_APPROVE,
    },
    "receptor": {
        PurchasePermissions.VIEW, PurchasePermissions.ORDER_VIEW,
        PurchasePermissions.RECEIPT_VIEW, PurchasePermissions.RECEIPT_COMPLETE,
    },
    "cuentas_por_pagar": {
        PurchasePermissions.VIEW, PurchasePermissions.INVOICE_VIEW,
        PurchasePermissions.INVOICE_CAPTURE, PurchasePermissions.INVOICE_MATCH,
    },
    "logistica_origen": {
        PurchasePermissions.VIEW, LogisticsPermissions.SHIPMENT_VIEW,
        LogisticsPermissions.SHIPMENT_CREATE, LogisticsPermissions.CONTAINER_SEAL,
        LogisticsPermissions.SHIPMENT_DISPATCH, LogisticsPermissions.SHIPMENT_OVERRIDE,
    },
    "solo_lectura": {PurchasePermissions.VIEW},
}


class _Session:
    user_id = "role-user"
    active_branch_id = "branch-1"
    active_warehouse_id = "warehouse-1"

    def __init__(self, grants):
        self._grants = grants

    def tiene_permiso(self, permission):
        return permission in self._grants


def _capabilities(role):
    return EnterprisePurchasingPresenter(
        connection_provider=lambda: None, read_services={}, analytics=None,
        use_cases={}, session_context=_Session(ROLE_GRANTS[role]),
    ).capabilities()


@pytest.mark.parametrize(
    ("role", "routes"),
    [
        ("solicitante", {PurchasingRoutes.DASHBOARD, PurchasingRoutes.REQUISITIONS}),
        ("comprador", {PurchasingRoutes.DASHBOARD, PurchasingRoutes.REQUISITIONS,
                       PurchasingRoutes.QUOTATIONS, PurchasingRoutes.ORDERS,
                       PurchasingRoutes.DIRECT_PURCHASE_CREATE,
                       PurchasingRoutes.DIRECT_PURCHASE_HISTORY}),
        ("aprobador", {PurchasingRoutes.DASHBOARD, PurchasingRoutes.REQUISITIONS,
                       PurchasingRoutes.ORDERS}),
        ("receptor", {PurchasingRoutes.DASHBOARD, PurchasingRoutes.ORDERS,
                      PurchasingRoutes.RECEIPTS}),
        ("cuentas_por_pagar", {PurchasingRoutes.DASHBOARD, PurchasingRoutes.INVOICES}),
        ("logistica_origen", {PurchasingRoutes.DASHBOARD, PurchasingRoutes.ORIGIN_LOADING}),
        ("solo_lectura", {PurchasingRoutes.DASHBOARD}),
    ],
)
def test_visible_routes_by_role(role, routes):
    assert {route.key for route in visible_routes(_capabilities(role))} == routes


def test_sensitive_actions_are_not_inferred_from_read_access():
    receiver = _capabilities("receptor")
    payable = _capabilities("cuentas_por_pagar")
    logistics = _capabilities("logistica_origen")

    assert receiver.receipt_complete and not receiver.invoice_match
    assert payable.invoice_match and not payable.order_approve
    assert logistics.origin_view and logistics.origin_create
    assert logistics.origin_seal and logistics.origin_dispatch and logistics.origin_override
    assert not logistics.receipt_complete
