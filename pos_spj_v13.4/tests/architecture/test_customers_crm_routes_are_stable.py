"""CRM-1 (§9, "No usar índices de pestañas como identidad") — routes are stable strings.

The canonical route ids are enumerated in
docs/refactor/customers_crm_master_prompt.md §9 (``customers.*``, ``crm.*``,
all dotted, none numeric). Once ``customers_crm_routes.py`` exists (CRM-14+)
it must not resolve any route to ``None`` and every route_id it defines must
use the ``customers.`` or ``crm.`` prefix — never a bare tab index. Mirrors
``test_transfers_ui_uses_design_system.py``'s route check for its own module.
Skipped until the routes file exists.
"""

from __future__ import annotations

import re

import pytest

from .customers_crm_guardrails import CRM_ROUTES_FILE, relative

_ROUTE_ID_RE = re.compile(r'route_id\s*=\s*["\']([^"\']+)["\']')
_TAB_INDEX_ROUTE = re.compile(r'route_id\s*=\s*["\']?\d+["\']?')


def test_customers_crm_routes_use_stable_dotted_ids():
    if not CRM_ROUTES_FILE.exists():
        pytest.skip(
            f"{relative(CRM_ROUTES_FILE)} does not exist yet — created in CRM-14+."
        )
    source = CRM_ROUTES_FILE.read_text(encoding="utf-8")

    assert "return None" not in source, (
        f"{relative(CRM_ROUTES_FILE)} resolves a route to None — every declared "
        "route must map to a page."
    )
    assert not _TAB_INDEX_ROUTE.search(source), (
        f"{relative(CRM_ROUTES_FILE)} uses a numeric tab index as a route id."
    )

    route_ids = _ROUTE_ID_RE.findall(source)
    assert route_ids, f"{relative(CRM_ROUTES_FILE)} declares no route_id."
    malformed = [r for r in route_ids if not (r.startswith("customers.") or r.startswith("crm."))]
    assert not malformed, (
        f"Route id(s) outside the canonical customers.*/crm.* namespace: {malformed}"
    )
