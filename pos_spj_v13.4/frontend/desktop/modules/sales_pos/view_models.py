"""View-model for the Sales/POS desktop workspace (POS-19).

Mirrors `frontend/desktop/modules/customers_crm/view_models.py::
CustomerCrmCapabilities` — one flag per capability group the workspace
gates, each mapped to an existing granular `SalesPermissions` code (all
already built across SALES-2..18, no new permission codes needed).
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SalesPosCapabilities:
    module_view: bool = False
    sale_create: bool = False
    line_edit: bool = False
    discount_apply: bool = False
    payment_cash: bool = False
    payment_card: bool = False
    payment_transfer: bool = False
    payment_credit: bool = False
    payment_mercado_pago: bool = False
    sale_complete: bool = False
    sale_suspend: bool = False
    sale_resume: bool = False
    sale_cancel: bool = False
    sale_return: bool = False
    sale_reverse: bool = False
    invoice_request: bool = False
    receipt_reprint: bool = False
    device_diagnostics: bool = False
