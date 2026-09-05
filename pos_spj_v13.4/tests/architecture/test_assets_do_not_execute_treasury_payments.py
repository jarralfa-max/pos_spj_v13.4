"""ASSET-1 (§2, §29, §54, §84, §110) — Activos never executes treasury payments.

The legacy `core/services/asset_service.py::completar_y_pagar_mantenimiento()`
called `treasury_service.registrar_gasto_opex(...)` directly — exactly the
pattern this guardrail exists to prevent in the new bounded context. The
correct flow is WorkOrder -> MAINTENANCE_COST_CONFIRMED event -> Finance/AP
decides -> Treasury executes. See docs/refactor/assets_finance_boundary_map.md.
"""

from __future__ import annotations

import re

from tests.architecture.assets_guardrails import ALL_ASSET_CODE_ROOTS, asset_py_files, relative

_FORBIDDEN = re.compile(
    r"treasury_service\s*\.\s*\w+\s*\("
    r"|registrar_gasto_opex\s*\("
    r"|registrar_pago\s*\("
    r"|\bTreasuryService\s*\("
    r"|completar_y_pagar\s*\(",
)


def test_assets_do_not_execute_treasury_payments():
    offenders = []
    for path in asset_py_files(ALL_ASSET_CODE_ROOTS):
        text = path.read_text(encoding="utf-8")
        for m in _FORBIDDEN.finditer(text):
            offenders.append(f"{relative(path)}: {m.group(0)!r}")
    assert not offenders, (
        "Activos intenta ejecutar pagos de Tesorería directamente "
        "(eso es responsabilidad de Finanzas/CxP/Tesorería):\n" + "\n".join(offenders)
    )
