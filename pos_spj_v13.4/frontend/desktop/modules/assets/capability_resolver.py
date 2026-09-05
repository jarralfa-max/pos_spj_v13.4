"""Single permission-to-capability map for the Activos UI (ASSET-16).

Mirrors ``frontend/desktop/modules/customers_crm/capability_resolver.py``.
Every capability reuses a granular permission already built in ASSET-2
(``backend.application.assets.permissions.AssetPermissions``) — no new
permission codes needed for this phase.
"""

from __future__ import annotations

from collections.abc import Callable

from backend.application.assets.permissions import AssetPermissions
from frontend.desktop.modules.assets.view_models import AssetsCapabilities


def resolve_assets_capabilities(can: Callable[[str], bool]) -> AssetsCapabilities:
    return AssetsCapabilities(
        module_view=can(AssetPermissions.VIEW),
        activos=can(AssetPermissions.VIEW),
        mantenimiento=can(AssetPermissions.MAINTENANCE_VIEW),
        costos=can(AssetPermissions.COST_VIEW),
        movimientos=can(AssetPermissions.TRANSFER_VIEW),
        control_fisico=can(AssetPermissions.PHYSICAL_INVENTORY_VIEW),
        documentacion=can(AssetPermissions.DOCUMENT_VIEW),
        bajas=can(AssetPermissions.DISPOSAL_VIEW),
        control=can(AssetPermissions.AUDIT_VIEW),
    )
