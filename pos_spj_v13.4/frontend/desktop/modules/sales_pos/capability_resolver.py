"""Single permission-to-capability map for the Sales/POS UI (POS-19).

Mirrors `frontend/desktop/modules/customers_crm/capability_resolver.py`.
Every capability reuses an existing granular `SalesPermissions` code
(built SALES-2, §61) — no new permission codes needed for this phase.
"""

from __future__ import annotations

from collections.abc import Callable

from backend.application.sales.permissions import SalesPermissions
from frontend.desktop.modules.sales_pos.view_models import SalesPosCapabilities


def resolve_sales_pos_capabilities(can: Callable[[str], bool]) -> SalesPosCapabilities:
    return SalesPosCapabilities(
        module_view=can(SalesPermissions.ACCESS),
        sale_create=can(SalesPermissions.SALE_CREATE),
        line_edit=can(SalesPermissions.LINE_ADD),
        discount_apply=can(SalesPermissions.DISCOUNT_APPLY),
        payment_cash=can(SalesPermissions.PAYMENT_CASH),
        payment_card=can(SalesPermissions.PAYMENT_CARD),
        payment_transfer=can(SalesPermissions.PAYMENT_TRANSFER),
        payment_credit=can(SalesPermissions.PAYMENT_CREDIT),
        payment_mercado_pago=can(SalesPermissions.PAYMENT_MERCADO_PAGO),
        sale_complete=can(SalesPermissions.SALE_COMPLETE),
        sale_suspend=can(SalesPermissions.SALE_SUSPEND),
        sale_resume=can(SalesPermissions.SALE_RESUME),
        sale_cancel=can(SalesPermissions.SALE_CANCEL),
        sale_return=can(SalesPermissions.RETURN),
        sale_reverse=can(SalesPermissions.REVERSE),
        invoice_request=can(SalesPermissions.INVOICE_REQUEST),
        receipt_reprint=can(SalesPermissions.RECEIPT_REPRINT),
        device_diagnostics=can(SalesPermissions.DEVICE_DIAGNOSTICS_VIEW),
    )
