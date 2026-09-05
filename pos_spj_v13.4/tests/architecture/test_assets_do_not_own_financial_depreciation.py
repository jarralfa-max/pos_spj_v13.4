"""ASSET-1 (§2, §33-35, §110) — Activos never calculates financial depreciation.

Finanzas owns depreciation method/basis/period calculation
(backend/domain/finance's FixedAsset.monthly_depreciation, etc.). Activos may
only show a read-only projection sourced from
AssetFinancialProjectionQueryService (a later ASSET phase). This targets
concrete computation entry points, not the mere presence of a descriptive
field like `expected_useful_life_months` (a legitimate operational attribute
on Asset, §11) — recomputing depreciation from it is what's forbidden.
"""

from __future__ import annotations

import re

from tests.architecture.assets_guardrails import (
    ASSET_APPLICATION_ROOT,
    ASSET_DOMAIN_ROOT,
    ASSET_UI_ROOT,
    asset_py_files,
    relative,
)

_FORBIDDEN = re.compile(
    r"calcular_depreciacion"
    r"|accrual_depreciacion"
    r"|monthly_depreciation"
    r"|depreciable_base"
    r"|remaining_depreciable"
    r"|net_book_value"
    r"|register_depreciation"
    r"|capitalizar_mantenimiento",
)


def test_assets_do_not_own_financial_depreciation():
    offenders = []
    for path in asset_py_files((ASSET_DOMAIN_ROOT, ASSET_APPLICATION_ROOT, ASSET_UI_ROOT)):
        text = path.read_text(encoding="utf-8")
        for m in _FORBIDDEN.finditer(text):
            offenders.append(f"{relative(path)}: {m.group(0)!r}")
    assert not offenders, (
        "Activos recalcula/posee depreciación financiera (eso es responsabilidad "
        "de Finanzas — Activos solo lee AssetFinancialProjectionQueryService):\n"
        + "\n".join(offenders)
    )
