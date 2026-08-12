"""CRM-1 (§60, "Los permisos deben evaluarse con scopes") — OWN/TEAM/BRANCH/....

The master prompt requires ``CustomerDataScopeResolver``/``CRMDataScopeResolver``
to filter reads by ``OWN, TEAM, BRANCH, TERRITORY, PORTFOLIO, COMPANY, ALL``.
This is a positive requirement with no code to check yet — CRM-2 is where the
scope resolver and the permission module land. Until then this test is
skipped with an explicit pointer (never a silent pass presented as
"satisfied"). Once ``backend/application/customers/permissions.py`` exists it
must expose at least one scope suffix per axis, following the
``ver.sucursal_propia`` / ``ver.sucursales_asignadas`` / ``ver.todas_sucursales``
precedent already used by CAJA/INVENTARIO/COMPRAS
(backend/application/cash_register/permissions.py).
"""

from __future__ import annotations

import pytest

from .customers_crm_guardrails import CRM_PERMISSIONS_FILE, relative

_REQUIRED_SCOPE_AXES = ("own", "team", "branch", "territory", "portfolio", "company")


def test_customers_crm_defines_data_scopes():
    if not CRM_PERMISSIONS_FILE.exists():
        pytest.skip(
            f"{relative(CRM_PERMISSIONS_FILE)} does not exist yet — CRM-2 must "
            "introduce it with OWN/TEAM/BRANCH/TERRITORY/PORTFOLIO/COMPANY scope "
            "suffixes (see master prompt §60-61). No scope resolver exists in "
            "this codebase for Clientes today (CRM_0 audit §9) — this is net-new."
        )
    lowered = CRM_PERMISSIONS_FILE.read_text(encoding="utf-8").lower()
    missing = [axis for axis in _REQUIRED_SCOPE_AXES if axis not in lowered]
    assert not missing, (
        f"{relative(CRM_PERMISSIONS_FILE)} is missing scope axes: {missing} "
        "(expected at least one permission suffix per OWN/TEAM/BRANCH/TERRITORY/"
        "PORTFOLIO/COMPANY)"
    )
