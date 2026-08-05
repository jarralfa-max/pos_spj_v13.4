"""Single source of truth mapping canonical permissions to display capabilities.

Shared by every Purchasing presenter (enterprise + direct purchase) so the two
never drift into two different permission→capability mappings.
"""

from __future__ import annotations

from typing import Callable

from backend.application.logistics.authorization import LogisticsPermissions
from backend.application.procurement.permissions import PurchasePermissions
from frontend.desktop.modules.purchasing.enterprise_view_models import PurchasingCapabilities


def resolve_purchasing_capabilities(can: Callable[[str], bool]) -> PurchasingCapabilities:
    P = PurchasePermissions
    L = LogisticsPermissions
    return PurchasingCapabilities(
        module_view=can(P.VIEW),
        requisition_view=can(P.REQUISITION_VIEW),
        requisition_create=can(P.REQUISITION_CREATE),
        requisition_submit=can(P.REQUISITION_SUBMIT),
        requisition_approve=can(P.REQUISITION_APPROVE),
        requisition_reject=can(P.REQUISITION_REJECT),
        rfq_create=can(P.RFQ_CREATE),
        order_view=can(P.ORDER_VIEW),
        order_create=can(P.ORDER_CREATE),
        order_approve=can(P.ORDER_APPROVE),
        order_send=can(P.ORDER_SEND),
        order_change=can(P.ORDER_CHANGE_APPROVED),
        receipt_view=can(P.RECEIPT_VIEW),
        receipt_complete=can(P.RECEIPT_COMPLETE),
        origin_view=can(L.SHIPMENT_VIEW),
        origin_create=can(L.SHIPMENT_CREATE),
        origin_seal=can(L.CONTAINER_SEAL),
        origin_dispatch=can(L.SHIPMENT_DISPATCH),
        origin_override=can(L.SHIPMENT_OVERRIDE),
        invoice_view=can(P.INVOICE_VIEW),
        invoice_capture=can(P.INVOICE_CAPTURE),
        invoice_match=can(P.INVOICE_MATCH),
        invoice_release_variance=can(P.INVOICE_RELEASE_VARIANCE),
        direct_view=can(P.DIRECT_VIEW),
        direct_create=can(P.DIRECT_CREATE),
        direct_authorize=can(P.OVERRIDE_FINANCIAL_LIMIT),
        direct_confirm=can(P.DIRECT_CONFIRM),
        direct_reverse=can(P.DIRECT_REVERSE),
        view_costs=can(P.VIEW_COSTS),
        view_analytics=can(P.VIEW_ANALYTICS),
    )
