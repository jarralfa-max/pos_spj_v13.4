"""Single permission-to-capability map for the Clientes y CRM UI (CRM-14).

Mirrors ``frontend/desktop/modules/cash_register/capability_resolver.py``.
Each capability reuses an existing granular permission from ``backend.
application.customers.permissions``/``backend.application.crm.permissions``
(built CRM-2 through CRM-13) — no new permission codes were needed for
this phase, since every nav group in §8 of the master prompt already maps
to a bounded-context area this pipeline already gated.
"""

from __future__ import annotations

from collections.abc import Callable

from backend.application.crm.permissions import CRMPermissions
from backend.application.customers.permissions import CustomerPermissions
from frontend.desktop.modules.customers_crm.view_models import CustomerCrmCapabilities


def resolve_customer_crm_capabilities(can: Callable[[str], bool]) -> CustomerCrmCapabilities:
    return CustomerCrmCapabilities(
        module_view=can(CustomerPermissions.ACCESS),
        clientes=can(CustomerPermissions.VIEW),
        prospectos=can(CRMPermissions.LEADS_VIEW),
        oportunidades=can(CRMPermissions.OPPORTUNITIES_VIEW),
        actividades=can(CRMPermissions.ACTIVITIES_VIEW),
        atencion=can(CRMPermissions.CASES_VIEW),
        comercial=can(CustomerPermissions.ORDERS_VIEW),
        credito=can(CustomerPermissions.CREDIT_VIEW),
        segmentacion=can(CRMPermissions.SEGMENTS_VIEW),
        comunicaciones=can(CustomerPermissions.CONSENT_VIEW),
        privacidad=can(CustomerPermissions.PRIVACY_REQUEST_VIEW),
        control=can(CustomerPermissions.DATA_QUALITY_VIEW),
    )
